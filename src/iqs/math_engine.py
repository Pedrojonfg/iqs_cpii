from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

try:
    from numba import njit
except Exception:  # pragma: no cover - numba is optional at runtime

    def njit(*args, **kwargs):  # type: ignore[misc]
        def _wrap(f):
            return f

        # Support both @njit and @njit(...)
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]
        return _wrap


Array1D = np.ndarray


@dataclass(frozen=True, slots=True)
class Garch11Params:
    """Parameters for a GARCH(1,1) model."""

    omega: float
    alpha: float
    beta: float


# ============================================================
# Microstructure & High-Frequency Indicators
# ============================================================


@njit(cache=True)
def order_book_imbalance(bid_size: float, ask_size: float) -> float:
    """
    Order Book Imbalance (OBI).

    Academic definition (top-of-book):
        OBI = (Q_bid - Q_ask) / (Q_bid + Q_ask)

    Range: [-1, +1]. Positive means bid-dominant.
    """
    denom = bid_size + ask_size
    if denom <= 0.0:
        return 0.0
    return (bid_size - ask_size) / denom


@njit(cache=True)
def micro_price(best_bid: float, best_ask: float, bid_size: float, ask_size: float) -> float:
    """
    Micro-Price (a.k.a. volume-weighted mid at top-of-book).

    Definition:
        P_micro = (P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)

    Intuition: shifts the mid-price towards the side with less available liquidity.
    """
    denom = bid_size + ask_size
    if denom <= 0.0:
        return 0.5 * (best_bid + best_ask)
    return (best_ask * bid_size + best_bid * ask_size) / denom


@njit(cache=True)
def bid_ask_spread(best_bid: float, best_ask: float, *, relative: bool = False) -> float:
    """
    Bid-Ask Spread.

    Absolute:
        S = P_ask - P_bid
    Relative (to mid):
        s = (P_ask - P_bid) / ((P_ask + P_bid)/2)
    """
    s = best_ask - best_bid
    if not relative:
        return s
    mid = 0.5 * (best_bid + best_ask)
    if mid == 0.0:
        return 0.0
    return s / mid


@njit(cache=True)
def market_depth(level_sizes: Array1D, *, levels: int = 1) -> float:
    """
    Market Depth (aggregate size across top N levels).

    If `level_sizes` are the sizes at each level, depth is:
        D_N = sum_{i=1..N} Q_i
    """
    n = min(levels, level_sizes.size)
    total = 0.0
    for i in range(n):
        q = level_sizes[i]
        if q > 0.0:
            total += q
    return total


@njit(cache=True)
def market_intensity_lambda(event_timestamps: Array1D) -> float:
    """
    Market intensity (λ) as a Poisson arrival rate estimator.

    For event timestamps t_1,...,t_n (seconds), MLE under homogeneous Poisson:
        λ_hat = n / (t_n - t_1)
    """
    n = event_timestamps.size
    if n < 2:
        return 0.0
    T = event_timestamps[n - 1] - event_timestamps[0]
    if T <= 0.0:
        return 0.0
    return n / T


@njit(cache=True)
def fill_probability_kappa(fill_indicators: Array1D, horizon_seconds: float) -> float:
    """
    Fill probability parameter κ under an exponential fill-time model.

    Model:
        P(Fill within t) = 1 - exp(-κ t)
    Empirical fill probability over horizon t:
        p_hat = mean(1{filled})
    Solve for κ (MLE under Bernoulli with exponential link):
        κ_hat = -ln(1 - p_hat) / t
    """
    if horizon_seconds <= 0.0:
        return 0.0
    n = fill_indicators.size
    if n == 0:
        return 0.0
    s = 0.0
    for i in range(n):
        s += 1.0 if fill_indicators[i] != 0.0 else 0.0
    p_hat = s / n
    if p_hat <= 0.0:
        return 0.0
    if p_hat >= 1.0:
        # Numerically: very large kappa; cap to a big number.
        return 1e9
    return -math.log(1.0 - p_hat) / horizon_seconds


@njit(cache=True)
def roll_yield(front_price: float, next_price: float, *, annualization_days: float = 252.0, roll_days: float = 21.0) -> float:
    """
    Roll yield for a two-contract term structure (front vs next).

    A common academic proxy:
        roll_yield_period = (P_next - P_front) / P_front
    Annualized over a typical roll horizon:
        roll_yield_annual = roll_yield_period * (annualization_days / roll_days)

    Notes:
    - For backwardation (P_next < P_front), roll yield is negative by this convention.
    - Some texts define with opposite sign; keep consistent with your portfolio accounting.
    """
    if front_price == 0.0 or roll_days <= 0.0:
        return 0.0
    period = (next_price - front_price) / front_price
    return period * (annualization_days / roll_days)


@njit(cache=True)
def slippage(
    exec_price: float,
    ref_price: float,
    side: float,
    *,
    in_bps: bool = False,
) -> float:
    """
    Slippage vs a reference price (arrival/mid/decision).

    Sign convention (academic trading cost):
        cost = side * (P_exec - P_ref)
    where side = +1 for BUY, -1 for SELL.

    - Positive cost => worse than reference (paying up on buys, selling lower on sells).
    - If in_bps=True, returns cost / P_ref * 1e4.
    """
    cost = side * (exec_price - ref_price)
    if not in_bps:
        return cost
    if ref_price == 0.0:
        return 0.0
    return (cost / ref_price) * 1e4


@njit(cache=True)
def implementation_shortfall(
    decision_price: float,
    exec_prices: Array1D,
    exec_qty: Array1D,
    side: float,
    total_qty: float,
    final_price: float,
    *,
    in_bps: bool = False,
) -> float:
    """
    Implementation Shortfall (IS) (Perold, 1988).

    For a BUY (side=+1):
        IS = sum(q_i * P_i) + (Q - sum q_i)*P_final - Q*P_decision
    For a SELL (side=-1) this same formula is captured by multiplying by side:
        IS = side * [sum(q_i * P_i) + (Q - sum q_i)*P_final - Q*P_decision]

    Returns *cost* (positive means worse execution).
    """
    n = exec_prices.size
    filled = 0.0
    notional = 0.0
    for i in range(n):
        q = exec_qty[i]
        if q <= 0.0:
            continue
        filled += q
        notional += q * exec_prices[i]
    remaining = total_qty - filled
    if remaining < 0.0:
        remaining = 0.0
    paper = total_qty * decision_price
    realized = notional + remaining * final_price
    is_cost = side * (realized - paper)
    if not in_bps:
        return is_cost
    if decision_price == 0.0 or total_qty == 0.0:
        return 0.0
    return (is_cost / (total_qty * decision_price)) * 1e4


@njit(cache=True)
def vwap(prices: Array1D, volumes: Array1D) -> float:
    """
    VWAP (Volume Weighted Average Price).

        VWAP = sum(P_t * V_t) / sum(V_t)
    """
    n = prices.size
    if n == 0 or volumes.size != n:
        return float("nan")
    pv = 0.0
    vv = 0.0
    for i in range(n):
        v = volumes[i]
        if v <= 0.0:
            continue
        pv += prices[i] * v
        vv += v
    if vv == 0.0:
        return float("nan")
    return pv / vv


@njit(cache=True)
def twap(prices: Array1D) -> float:
    """
    TWAP (Time Weighted Average Price) assuming equally spaced samples.

        TWAP = mean(P_t)
    """
    n = prices.size
    if n == 0:
        return float("nan")
    s = 0.0
    for i in range(n):
        s += prices[i]
    return s / n


@njit(cache=True)
def vpin(
    signed_volume: Array1D,
    bucket_volume: float,
) -> float:
    """
    VPIN (Volume-Synchronized Probability of Informed Trading) proxy.

    Original intuition (Easley, López de Prado, O'Hara):
        VPIN ≈ E[ |V_buy - V_sell| / V_bucket ]
    computed over equal-volume buckets.

    Input:
    - signed_volume: array of trade volumes with sign (+ for buy-initiated, - for sell-initiated)
    - bucket_volume: target absolute volume per bucket

    Output:
    - mean bucket imbalance ratio in [0, 1] (approximately)
    """
    if bucket_volume <= 0.0:
        return float("nan")
    n = signed_volume.size
    if n == 0:
        return float("nan")

    # Build equal-volume buckets using absolute volume.
    bucket_abs = 0.0
    bucket_imb = 0.0  # V_buy - V_sell, captured by signed sum
    sum_ratio = 0.0
    buckets = 0

    for i in range(n):
        sv = signed_volume[i]
        av = abs(sv)
        if av <= 0.0:
            continue

        # Consume volume into current bucket potentially in parts.
        remaining = av
        direction = 1.0 if sv >= 0.0 else -1.0
        while remaining > 0.0:
            capacity = bucket_volume - bucket_abs
            take = remaining if remaining < capacity else capacity
            bucket_abs += take
            bucket_imb += direction * take
            remaining -= take

            if bucket_abs >= bucket_volume - 1e-12:
                sum_ratio += abs(bucket_imb) / bucket_volume
                buckets += 1
                bucket_abs = 0.0
                bucket_imb = 0.0

    if buckets == 0:
        return float("nan")
    return sum_ratio / buckets


# ============================================================
# Statistical & Time Series Indicators
# ============================================================


@njit(cache=True)
def log_returns(prices: Array1D) -> Array1D:
    """
    Log-returns.

        r_t = ln(P_t / P_{t-1})

    Returns an array of length n-1.
    """
    n = prices.size
    if n < 2:
        return np.empty(0, dtype=np.float64)
    out = np.empty(n - 1, dtype=np.float64)
    for i in range(1, n):
        p0 = prices[i - 1]
        p1 = prices[i]
        if p0 <= 0.0 or p1 <= 0.0:
            out[i - 1] = float("nan")
        else:
            out[i - 1] = math.log(p1 / p0)
    return out


@njit(cache=True)
def z_score(x: Array1D) -> Array1D:
    """
    Z-score standardization.

        z_i = (x_i - mean(x)) / std(x)
    """
    n = x.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    mu = 0.0
    for i in range(n):
        mu += x[i]
    mu /= n
    var = 0.0
    for i in range(n):
        d = x[i] - mu
        var += d * d
    var /= n
    sd = math.sqrt(var)
    if sd == 0.0 or math.isnan(sd):
        for i in range(n):
            out[i] = 0.0
        return out
    for i in range(n):
        out[i] = (x[i] - mu) / sd
    return out


@njit(cache=True)
def skewness(x: Array1D) -> float:
    """
    Sample skewness (moment-based).

        g1 = m3 / m2^(3/2)
    where m_k are central moments with denominator n.
    """
    n = x.size
    if n == 0:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += x[i]
    mu /= n
    m2 = 0.0
    m3 = 0.0
    for i in range(n):
        d = x[i] - mu
        d2 = d * d
        m2 += d2
        m3 += d2 * d
    m2 /= n
    m3 /= n
    if m2 <= 0.0:
        return 0.0
    return m3 / (m2 ** 1.5)


@njit(cache=True)
def kurtosis_excess(x: Array1D) -> float:
    """
    Excess kurtosis (moment-based).

        g2 = m4 / m2^2 - 3
    """
    n = x.size
    if n == 0:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += x[i]
    mu /= n
    m2 = 0.0
    m4 = 0.0
    for i in range(n):
        d = x[i] - mu
        d2 = d * d
        m2 += d2
        m4 += d2 * d2
    m2 /= n
    m4 /= n
    if m2 <= 0.0:
        return -3.0
    return m4 / (m2 * m2) - 3.0


@njit(cache=True)
def jarque_bera(x: Array1D) -> float:
    """
    Jarque–Bera normality test statistic.

        JB = (n/6) * (S^2 + (K^2)/4)

    Where:
    - S is skewness
    - K is excess kurtosis

    p-value under H0 is approx chi-square with 2 dof (not returned here).
    """
    n = x.size
    if n < 2:
        return float("nan")
    s = skewness(x)
    k = kurtosis_excess(x)
    return (n / 6.0) * (s * s + 0.25 * k * k)


@njit(cache=True)
def hurst_exponent_rs(x: Array1D, *, min_window: int = 10, max_window: int = 200) -> float:
    """
    Hurst exponent via Rescaled Range (R/S) analysis.

    For window size m:
      1) compute mean-adjusted series
      2) compute cumulative deviate Y(k)
      3) R = max(Y) - min(Y)
      4) S = std(x)
      5) R/S ~ c * m^H  => log(R/S) ~ H*log(m) + const

    Returns slope H from an OLS fit on log-log points.
    """
    n = x.size
    if n < 2 * min_window:
        return float("nan")

    # Build window sizes (integer steps).
    if max_window > n // 2:
        max_window = n // 2
    if max_window < min_window:
        return float("nan")

    # Use a sparse grid of window sizes for speed.
    count = 0
    for m in range(min_window, max_window + 1):
        if m == min_window or m == max_window or (m % 10 == 0):
            count += 1
    if count < 2:
        return float("nan")

    log_m = np.empty(count, dtype=np.float64)
    log_rs = np.empty(count, dtype=np.float64)

    idx = 0
    for m in range(min_window, max_window + 1):
        if not (m == min_window or m == max_window or (m % 10 == 0)):
            continue
        # Use non-overlapping windows to keep it simple/academic.
        k_windows = n // m
        if k_windows < 1:
            continue
        rs_sum = 0.0
        used = 0
        for w in range(k_windows):
            start = w * m
            end = start + m
            mu = 0.0
            for i in range(start, end):
                mu += x[i]
            mu /= m
            # Std
            var = 0.0
            for i in range(start, end):
                d = x[i] - mu
                var += d * d
            var /= m
            s = math.sqrt(var)
            if s <= 0.0:
                continue
            # Cumulative deviate
            y = 0.0
            y_max = -1e300
            y_min = 1e300
            for i in range(start, end):
                y += x[i] - mu
                if y > y_max:
                    y_max = y
                if y < y_min:
                    y_min = y
            r = y_max - y_min
            if r <= 0.0:
                continue
            rs_sum += r / s
            used += 1
        if used < 1:
            continue
        rs = rs_sum / used
        if rs <= 0.0:
            continue
        log_m[idx] = math.log(m)
        log_rs[idx] = math.log(rs)
        idx += 1

    if idx < 2:
        return float("nan")

    # OLS slope
    xm = 0.0
    ym = 0.0
    for i in range(idx):
        xm += log_m[i]
        ym += log_rs[i]
    xm /= idx
    ym /= idx
    num = 0.0
    den = 0.0
    for i in range(idx):
        dx = log_m[i] - xm
        dy = log_rs[i] - ym
        num += dx * dy
        den += dx * dx
    if den <= 0.0:
        return float("nan")
    return num / den


@njit(cache=True)
def adf_tstat(y: Array1D, *, lags: int = 1, include_const: bool = True) -> float:
    """
    Augmented Dickey-Fuller test (ADF) t-statistic for unit root.

    Regression (no trend; optionally with intercept):
        Δy_t = c + γ y_{t-1} + Σ_{i=1..p} φ_i Δy_{t-i} + ε_t

    H0: γ = 0 (unit root). We return the t-statistic for γ.
    (Critical values/p-values depend on non-standard distributions; not returned.)
    """
    n = y.size
    p = lags
    if n < p + 3:
        return float("nan")

    # Build Δy and lagged terms.
    dy = np.empty(n - 1, dtype=np.float64)
    for t in range(1, n):
        dy[t - 1] = y[t] - y[t - 1]

    # Effective sample: t = p .. (n-2) in dy-index, corresponds to y-index (t+1)
    T = (n - 1) - p
    if T <= 1:
        return float("nan")

    k = (1 if include_const else 0) + 1 + p  # const + y_{t-1} + p lagged Δy
    X = np.empty((T, k), dtype=np.float64)
    Y = np.empty(T, dtype=np.float64)

    for i in range(T):
        t = p + i  # dy index
        Y[i] = dy[t]
        col = 0
        if include_const:
            X[i, col] = 1.0
            col += 1
        # y_{t} is y_{(t)} in y-index since dy[t] = y[t+1]-y[t]
        X[i, col] = y[t]
        col += 1
        for j in range(1, p + 1):
            X[i, col] = dy[t - j]
            col += 1

    # OLS: beta = (X'X)^{-1} X'Y
    XtX = np.zeros((k, k), dtype=np.float64)
    XtY = np.zeros(k, dtype=np.float64)
    for i in range(T):
        for a in range(k):
            XtY[a] += X[i, a] * Y[i]
            for b in range(k):
                XtX[a, b] += X[i, a] * X[i, b]

    # Invert XtX via Gauss-Jordan (small k).
    A = np.zeros((k, 2 * k), dtype=np.float64)
    for i in range(k):
        for j in range(k):
            A[i, j] = XtX[i, j]
        A[i, k + i] = 1.0

    for i in range(k):
        piv = A[i, i]
        if abs(piv) < 1e-14:
            return float("nan")
        inv_piv = 1.0 / piv
        for j in range(2 * k):
            A[i, j] *= inv_piv
        for r in range(k):
            if r == i:
                continue
            f = A[r, i]
            if f == 0.0:
                continue
            for j in range(2 * k):
                A[r, j] -= f * A[i, j]

    XtX_inv = np.zeros((k, k), dtype=np.float64)
    for i in range(k):
        for j in range(k):
            XtX_inv[i, j] = A[i, k + j]

    beta = np.zeros(k, dtype=np.float64)
    for i in range(k):
        for j in range(k):
            beta[i] += XtX_inv[i, j] * XtY[j]

    # Residual variance
    sse = 0.0
    for i in range(T):
        yhat = 0.0
        for j in range(k):
            yhat += X[i, j] * beta[j]
        e = Y[i] - yhat
        sse += e * e
    dof = T - k
    if dof <= 0:
        return float("nan")
    sigma2 = sse / dof

    # Std error of gamma coefficient (the y_{t-1} regressor)
    gamma_idx = (1 if include_const else 0)
    se2 = sigma2 * XtX_inv[gamma_idx, gamma_idx]
    if se2 <= 0.0:
        return float("nan")
    se = math.sqrt(se2)
    return beta[gamma_idx] / se


@njit(cache=True)
def half_life_mean_reversion(x: Array1D) -> float:
    """
    Half-life of mean reversion under an OU / AR(1) approximation.

    Regress:
        Δx_t = a + b x_{t-1} + ε_t
    If b < 0, the half-life (time to decay by 50%) is:
        HL = -ln(2) / b
    """
    n = x.size
    if n < 3:
        return float("nan")

    # Build y = Δx, regressor = x_{t-1} with intercept.
    T = n - 1
    sum_x = 0.0
    sum_y = 0.0
    sum_x2 = 0.0
    sum_xy = 0.0
    for t in range(1, n):
        xtm1 = x[t - 1]
        yt = x[t] - x[t - 1]
        sum_x += xtm1
        sum_y += yt
        sum_x2 += xtm1 * xtm1
        sum_xy += xtm1 * yt

    # OLS with intercept: b = cov(x,y) / var(x)
    mx = sum_x / T
    my = sum_y / T
    cov = sum_xy / T - mx * my
    var = sum_x2 / T - mx * mx
    if var <= 0.0:
        return float("nan")
    b = cov / var
    if b >= 0.0:
        return float("inf")
    return -math.log(2.0) / b


@njit(cache=True)
def beta(asset_returns: Array1D, benchmark_returns: Array1D) -> float:
    """
    CAPM beta:

        β = Cov(r_a, r_m) / Var(r_m)
    """
    n = asset_returns.size
    if n == 0 or benchmark_returns.size != n:
        return float("nan")
    ma = 0.0
    mb = 0.0
    for i in range(n):
        ma += asset_returns[i]
        mb += benchmark_returns[i]
    ma /= n
    mb /= n
    cov = 0.0
    var = 0.0
    for i in range(n):
        da = asset_returns[i] - ma
        db = benchmark_returns[i] - mb
        cov += da * db
        var += db * db
    if var <= 0.0:
        return float("nan")
    return cov / var


# ----------------------------
# GARCH(1,1) volatility
# ----------------------------


@njit(cache=True)
def _garch11_negloglik(returns: Array1D, omega: float, alpha: float, beta_: float) -> float:
    """
    Gaussian negative log-likelihood for GARCH(1,1):
        σ_t^2 = ω + α ε_{t-1}^2 + β σ_{t-1}^2
        ε_t = r_t - μ (we assume μ=0 for simplicity)
    """
    n = returns.size
    if n < 2:
        return float("inf")
    if omega <= 0.0 or alpha < 0.0 or beta_ < 0.0 or (alpha + beta_) >= 0.999999:
        return float("inf")

    # Initialize with unconditional variance (or sample variance fallback)
    mu = 0.0
    var = 0.0
    for i in range(n):
        d = returns[i] - mu
        var += d * d
    var /= n
    if var <= 0.0:
        var = 1e-12

    sigma2 = var
    nll = 0.0
    for t in range(n):
        eps = returns[t] - mu
        if sigma2 <= 0.0:
            return float("inf")
        nll += 0.5 * (math.log(2.0 * math.pi) + math.log(sigma2) + (eps * eps) / sigma2)
        sigma2 = omega + alpha * (eps * eps) + beta_ * sigma2
    return nll


def garch11_fit_mle(returns: Array1D, *, x0: Garch11Params | None = None) -> Garch11Params:
    """
    GARCH(1,1) MLE fit (Gaussian QMLE) using SciPy optimizer.

    Returns (ω, α, β). The likelihood core is numba-friendly; the optimizer is Python/SciPy.
    """
    from scipy.optimize import minimize

    r = np.asarray(returns, dtype=np.float64)
    if x0 is None:
        # Simple, common starting point.
        x0 = Garch11Params(omega=1e-6, alpha=0.05, beta=0.9)

    def obj(theta: np.ndarray) -> float:
        return float(_garch11_negloglik(r, float(theta[0]), float(theta[1]), float(theta[2])))

    bounds = [(1e-12, None), (0.0, 1.0), (0.0, 1.0)]
    cons = [{"type": "ineq", "fun": lambda th: 0.999999 - (th[1] + th[2])}]

    res = minimize(obj, x0=np.array([x0.omega, x0.alpha, x0.beta], dtype=np.float64), bounds=bounds, constraints=cons)
    w, a, b = (float(res.x[0]), float(res.x[1]), float(res.x[2]))
    return Garch11Params(omega=w, alpha=a, beta=b)


@njit(cache=True)
def garch11_conditional_volatility(returns: Array1D, params: Garch11Params) -> Array1D:
    """
    Conditional volatility series σ_t for GARCH(1,1), assuming μ=0.
    """
    n = returns.size
    out = np.empty(n, dtype=np.float64)
    if n == 0:
        return out
    # Sample variance init
    var = 0.0
    for i in range(n):
        var += returns[i] * returns[i]
    var /= n
    if var <= 0.0:
        var = 1e-12
    sigma2 = var
    for t in range(n):
        if sigma2 <= 0.0:
            sigma2 = 1e-12
        out[t] = math.sqrt(sigma2)
        eps = returns[t]
        sigma2 = params.omega + params.alpha * (eps * eps) + params.beta * sigma2
    return out


# ============================================================
# Performance & Risk Metrics
# ============================================================


@njit(cache=True)
def sharpe_ratio(returns: Array1D, risk_free_rate: float = 0.0, annualization: float = 252.0) -> float:
    """
    Sharpe ratio (annualized).

        SR = sqrt(A) * mean(r - r_f) / std(r - r_f)
    where A is annualization factor (e.g. 252 for daily).
    """
    n = returns.size
    if n < 2:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += returns[i] - risk_free_rate
    mu /= n
    var = 0.0
    for i in range(n):
        d = (returns[i] - risk_free_rate) - mu
        var += d * d
    var /= (n - 1)
    sd = math.sqrt(var)
    if sd <= 0.0:
        return float("nan")
    return math.sqrt(annualization) * (mu / sd)


@njit(cache=True)
def maximum_drawdown(equity_curve: Array1D) -> float:
    """
    Maximum drawdown (MDD) on an equity curve.

        DD_t = (peak_to_date - equity_t) / peak_to_date
        MDD = max_t DD_t
    """
    n = equity_curve.size
    if n == 0:
        return float("nan")
    peak = equity_curve[0]
    mdd = 0.0
    for i in range(n):
        v = equity_curve[i]
        if v > peak:
            peak = v
        if peak > 0.0:
            dd = (peak - v) / peak
            if dd > mdd:
                mdd = dd
    return mdd


@njit(cache=True)
def calmar_ratio(returns: Array1D, equity_curve: Array1D, annualization: float = 252.0) -> float:
    """
    Calmar ratio.

        Calmar = CAGR / MDD
    Here we approximate CAGR using mean returns:
        CAGR ≈ (1 + mean(r))^A - 1
    """
    n = returns.size
    if n == 0:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += returns[i]
    mu /= n
    cagr = (1.0 + mu) ** annualization - 1.0
    mdd = maximum_drawdown(equity_curve)
    if mdd <= 0.0:
        return float("inf")
    return cagr / mdd


@njit(cache=True)
def var_historical(returns: Array1D, alpha: float = 0.05) -> float:
    """
    Historical Value at Risk (VaR) at level alpha for returns.

    VaR_alpha is the alpha-quantile of the return distribution (loss tail).
    Convention: returns are P&L in return units; VaR is negative for loss.
    """
    n = returns.size
    if n == 0:
        return float("nan")
    x = np.sort(returns.copy())
    idx = int(math.floor(alpha * (n - 1)))
    if idx < 0:
        idx = 0
    if idx > n - 1:
        idx = n - 1
    return x[idx]


@njit(cache=True)
def cvar_historical(returns: Array1D, alpha: float = 0.05) -> float:
    """
    Historical Expected Shortfall (CVaR/ES) at level alpha for returns.

        ES_alpha = E[r | r <= VaR_alpha]
    """
    n = returns.size
    if n == 0:
        return float("nan")
    v = var_historical(returns, alpha=alpha)
    s = 0.0
    c = 0
    for i in range(n):
        if returns[i] <= v:
            s += returns[i]
            c += 1
    if c == 0:
        return v
    return s / c


@njit(cache=True)
def kelly_fraction(mean_return: float, var_return: float) -> float:
    """
    Kelly criterion fraction for i.i.d. returns (small-return approximation).

    For a single risky bet with mean μ and variance σ^2:
        f* ≈ μ / σ^2
    """
    if var_return <= 0.0:
        return float("nan")
    return mean_return / var_return


@njit(cache=True)
def tracking_error(active_returns: Array1D, annualization: float = 252.0) -> float:
    """
    Tracking error (annualized): std of active returns.
    """
    n = active_returns.size
    if n < 2:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += active_returns[i]
    mu /= n
    var = 0.0
    for i in range(n):
        d = active_returns[i] - mu
        var += d * d
    var /= (n - 1)
    return math.sqrt(var) * math.sqrt(annualization)


@njit(cache=True)
def information_ratio(active_returns: Array1D, annualization: float = 252.0) -> float:
    """
    Information Ratio (IR):

        IR = sqrt(A) * mean(active) / std(active)
    """
    n = active_returns.size
    if n < 2:
        return float("nan")
    mu = 0.0
    for i in range(n):
        mu += active_returns[i]
    mu /= n
    var = 0.0
    for i in range(n):
        d = active_returns[i] - mu
        var += d * d
    var /= (n - 1)
    sd = math.sqrt(var)
    if sd <= 0.0:
        return float("nan")
    return math.sqrt(annualization) * (mu / sd)


def deflated_sharpe_ratio(
    sharpe: float,
    n_obs: int,
    *,
    sharpe_benchmark: float = 0.0,
    skew: float = 0.0,
    kurt_excess: float = 0.0,
) -> float:
    """
    Deflated Sharpe Ratio (DSR) (Bailey & López de Prado, 2012) approximation.

    A commonly used approximation adjusts SR for non-normality and sample size.
    Here we return an approximate z-score:

        z ≈ (SR - SR0) * sqrt(n - 1) / sqrt( 1 - S*SR + ((K-1)/4)*SR^2 )

    where:
      - SR0 is a benchmark SR (e.g., 0)
      - S is skewness, K is kurtosis (not excess) -> K = kurt_excess + 3

    Note: Full DSR includes multiple-testing / selection bias corrections (not included here).
    """
    if n_obs < 2:
        return float("nan")
    K = kurt_excess + 3.0
    denom = 1.0 - skew * sharpe + ((K - 1.0) / 4.0) * (sharpe * sharpe)
    if denom <= 0.0:
        return float("nan")
    return (sharpe - sharpe_benchmark) * math.sqrt(n_obs - 1) / math.sqrt(denom)


# ============================================================
# Advanced & Optimization Indicators
# ============================================================


@njit(cache=True)
def l1_norm(x: Array1D) -> float:
    """L1 norm: ||x||_1 = Σ |x_i|."""
    s = 0.0
    for i in range(x.size):
        s += abs(x[i])
    return s


@njit(cache=True)
def l2_norm(x: Array1D) -> float:
    """L2 norm: ||x||_2 = sqrt(Σ x_i^2)."""
    s = 0.0
    for i in range(x.size):
        s += x[i] * x[i]
    return math.sqrt(s)


def jacobian_fd(
    f: Callable[[Array1D], Array1D],
    x: Array1D,
    eps: float = 1e-6,
) -> np.ndarray:
    """
    Jacobian via central finite differences (academic baseline).

        J_{ij} = ∂f_i/∂x_j ≈ (f(x+e_j*eps) - f(x-e_j*eps)) / (2 eps)
    """
    x = np.asarray(x, dtype=np.float64)
    fx = np.asarray(f(x), dtype=np.float64)
    m = fx.size
    n = x.size
    J = np.empty((m, n), dtype=np.float64)
    for j in range(n):
        x1 = x.copy()
        x2 = x.copy()
        x1[j] += eps
        x2[j] -= eps
        f1 = np.asarray(f(x1), dtype=np.float64)
        f2 = np.asarray(f(x2), dtype=np.float64)
        J[:, j] = (f1 - f2) / (2.0 * eps)
    return J


def hessian_fd(
    f: Callable[[Array1D], float],
    x: Array1D,
    eps: float = 1e-5,
) -> np.ndarray:
    """
    Hessian via central finite differences (scalar-valued f).

        H_{ij} = ∂²f/∂x_i∂x_j

    Using a symmetric 2D central difference scheme.
    """
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    H = np.empty((n, n), dtype=np.float64)
    fx = float(f(x))
    for i in range(n):
        for j in range(i, n):
            if i == j:
                xp = x.copy()
                xm = x.copy()
                xp[i] += eps
                xm[i] -= eps
                H[i, i] = (float(f(xp)) - 2.0 * fx + float(f(xm))) / (eps * eps)
            else:
                xpp = x.copy()
                xpm = x.copy()
                xmp = x.copy()
                xmm = x.copy()
                xpp[i] += eps
                xpp[j] += eps
                xpm[i] += eps
                xpm[j] -= eps
                xmp[i] -= eps
                xmp[j] += eps
                xmm[i] -= eps
                xmm[j] -= eps
                val = (float(f(xpp)) - float(f(xpm)) - float(f(xmp)) + float(f(xmm))) / (4.0 * eps * eps)
                H[i, j] = val
                H[j, i] = val
    return H


@njit(cache=True)
def mean_squared_error(y_true: Array1D, y_pred: Array1D) -> float:
    """MSE: mean((y_true - y_pred)^2)."""
    n = y_true.size
    if n == 0 or y_pred.size != n:
        return float("nan")
    s = 0.0
    for i in range(n):
        d = y_true[i] - y_pred[i]
        s += d * d
    return s / n


@njit(cache=True)
def standardized_residuals(residuals: Array1D) -> Array1D:
    """
    Standardized residuals:
        z_t = (ε_t - mean(ε)) / std(ε)
    """
    return z_score(residuals)


@njit(cache=True)
def correlation_matrix(X: np.ndarray) -> np.ndarray:
    """
    Correlation matrix for a data matrix X with shape (n_obs, n_vars).
    """
    n_obs, n_vars = X.shape
    C = np.empty((n_vars, n_vars), dtype=np.float64)
    # Means
    mu = np.zeros(n_vars, dtype=np.float64)
    for j in range(n_vars):
        s = 0.0
        for i in range(n_obs):
            s += X[i, j]
        mu[j] = s / n_obs

    # Std devs
    sd = np.zeros(n_vars, dtype=np.float64)
    for j in range(n_vars):
        v = 0.0
        for i in range(n_obs):
            d = X[i, j] - mu[j]
            v += d * d
        v /= (n_obs - 1) if n_obs > 1 else 1
        sd[j] = math.sqrt(v)

    for a in range(n_vars):
        for b in range(n_vars):
            if sd[a] <= 0.0 or sd[b] <= 0.0:
                C[a, b] = 0.0
                continue
            cov = 0.0
            for i in range(n_obs):
                cov += (X[i, a] - mu[a]) * (X[i, b] - mu[b])
            cov /= (n_obs - 1) if n_obs > 1 else 1
            C[a, b] = cov / (sd[a] * sd[b])
    return C


def pca_eigenvalues(X: np.ndarray) -> np.ndarray:
    """
    Eigenvalues of the covariance matrix (PCA spectrum).

    Academic PCA: eigenvalues of Σ = cov(X), with X shaped (n_obs, n_vars).
    """
    X = np.asarray(X, dtype=np.float64)
    # Center
    Xc = X - X.mean(axis=0, keepdims=True)
    cov = (Xc.T @ Xc) / (Xc.shape[0] - 1)
    vals = np.linalg.eigvalsh(cov)
    return vals[::-1]


def cholesky_decomposition(A: np.ndarray) -> np.ndarray:
    """
    Cholesky decomposition (lower-triangular) for SPD matrix A.
    """
    A = np.asarray(A, dtype=np.float64)
    return np.linalg.cholesky(A)


def mle_normal_params(x: Array1D) -> tuple[float, float]:
    """
    MLE for Normal(μ, σ²).

        μ_hat = mean(x)
        σ²_hat = mean((x-μ_hat)^2)   (note: denominator n, not n-1)
    """
    x = np.asarray(x, dtype=np.float64)
    mu = float(x.mean()) if x.size else float("nan")
    var = float(((x - mu) ** 2).mean()) if x.size else float("nan")
    return mu, var


__all__ = [
    # Microstructure
    "order_book_imbalance",
    "micro_price",
    "vpin",
    "bid_ask_spread",
    "market_depth",
    "market_intensity_lambda",
    "fill_probability_kappa",
    "roll_yield",
    "slippage",
    "implementation_shortfall",
    "vwap",
    "twap",
    # Stats & time series
    "z_score",
    "hurst_exponent_rs",
    "adf_tstat",
    "half_life_mean_reversion",
    "garch11_fit_mle",
    "garch11_conditional_volatility",
    "skewness",
    "kurtosis_excess",
    "jarque_bera",
    "mle_normal_params",
    "log_returns",
    "beta",
    # Performance & risk
    "sharpe_ratio",
    "deflated_sharpe_ratio",
    "maximum_drawdown",
    "calmar_ratio",
    "var_historical",
    "cvar_historical",
    "kelly_fraction",
    "information_ratio",
    "tracking_error",
    # Advanced
    "l1_norm",
    "l2_norm",
    "jacobian_fd",
    "hessian_fd",
    "mean_squared_error",
    "standardized_residuals",
    "pca_eigenvalues",
    "correlation_matrix",
    "cholesky_decomposition",
    # Types
    "Garch11Params",
]

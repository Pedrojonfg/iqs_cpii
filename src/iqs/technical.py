from __future__ import annotations

import json
import math
import os
from typing import Any

import numpy as np
import pandas as pd

from iqs.math_engine import (
    garch11_conditional_volatility,
    garch11_fit_mle,
    hurst_exponent_rs,
    log_returns,
    z_score,
)


def _get_env_json(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON in environment variable {name}") from e
    if not isinstance(value, dict):
        raise RuntimeError(f"Environment variable {name} must be a JSON object")
    return value


def _clamp_positive_int(value: Any, *, default: int) -> int:
    try:
        iv = int(value)
    except Exception:
        return default
    return iv if iv > 0 else default


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        fv = float(value)
    except Exception:
        return default
    return fv


def _download_ohlcv(symbol: str, *, period: str, interval: str) -> pd.DataFrame:
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "yfinance is required for the default OHLCV downloader. "
            "Install it or patch `_download_ohlcv` in tests."
        ) from e

    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    # yfinance may return multiindex columns depending on version; normalize.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]) for c in df.columns]
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    return df.dropna(subset=["close"])


def _strategy_me_simple_v1(df: pd.DataFrame, params: dict[str, Any]) -> dict[str, Any]:
    """
    Simple, VPS-friendly strategy using ONLY `iqs.math_engine` indicators.

    Data: close prices.
    Indicators:
    - Hurst exponent (trend regime filter)
    - z-score of recent log-returns (entry/exit trigger)
    - GARCH(1,1) conditional vol on returns (volatility filter)
    """
    closes = np.asarray(df["close"].to_numpy(), dtype=np.float64)
    closes = closes[np.isfinite(closes)]
    if closes.size < 80:
        return {"signal": "DON'T BUY"}

    r = log_returns(closes)
    r = r[np.isfinite(r)]
    if r.size < 60:
        return {"signal": "DON'T BUY"}

    z_window = _clamp_positive_int(params.get("z_window"), default=20)
    if r.size < z_window + 2:
        return {"signal": "DON'T BUY"}
    z_last = float(z_score(r[-z_window:])[-1])

    hurst_min = _clamp_float(params.get("hurst_min"), default=0.55)
    hurst_max = _clamp_float(params.get("hurst_max"), default=0.45)
    h = float(hurst_exponent_rs(closes, min_window=10, max_window=min(200, int(closes.size // 2))))
    if not np.isfinite(h):
        # Deterministic / low-variance series can produce NaNs; use a neutral fallback.
        h = 0.5

    # Vol filter: fit once on the most recent window of returns.
    vol_window = _clamp_positive_int(params.get("vol_window"), default=120)
    vol_window = min(vol_window, int(r.size))
    r_fit = r[-vol_window:]
    vol_cap = _clamp_float(params.get("vol_cap"), default=0.03)  # per-bar sigma (daily if interval=1d)
    try:
        gparams = garch11_fit_mle(r_fit)
        vol_series = garch11_conditional_volatility(r_fit, gparams)
        sigma_last = float(vol_series[-1]) if vol_series.size else float("nan")
    except Exception:
        sigma_last = float("nan")
    if not np.isfinite(sigma_last):
        # Fallback volatility proxy.
        sigma_last = float(np.std(r_fit)) if r_fit.size else float("nan")

    entry_z = _clamp_float(params.get("entry_z"), default=1.0)
    exit_z = _clamp_float(params.get("exit_z"), default=-1.0)

    tp_pct = _clamp_float(params.get("take_profit_pct"), default=0.06)
    sl_pct = _clamp_float(params.get("stop_loss_pct"), default=0.03)
    px = float(closes[-1])

    # Conservative: if vol can't be computed, avoid entries.
    vol_ok = bool(np.isfinite(sigma_last) and sigma_last <= vol_cap)

    if vol_ok and h >= hurst_min and z_last >= entry_z:
        return {
            "signal": "BUY",
            "entry_price": px,
            "take_profit": px * (1.0 + tp_pct),
            "stop_loss": px * (1.0 - sl_pct),
        }

    # Exit: either negative shock or loss of trend regime.
    if np.isfinite(z_last) and z_last <= exit_z:
        return {"signal": "SELL", "entry_price": px}
    if h <= hurst_max and z_last < 0.0:
        return {"signal": "SELL", "entry_price": px}

    return {"signal": "DON'T BUY"}


_STRATEGIES: dict[str, Any] = {
    "me_simple_v1": _strategy_me_simple_v1,
}


class TechnicalAnalyzer:
    """Config-driven technical analysis engine."""

    def __init__(self) -> None:
        self.strategy_name: str = os.getenv("IQS_STRATEGY", "me_simple_v1").strip() or "me_simple_v1"
        self.strategy_params: dict[str, Any] = _get_env_json("IQS_STRATEGY_PARAMS")

        # MVP data source settings (yfinance). Replace with IB candles later.
        self.yf_period: str = os.getenv("IQS_YF_PERIOD", "6mo").strip() or "6mo"
        self.yf_interval: str = os.getenv("IQS_YF_INTERVAL", "1d").strip() or "1d"

        # Sizing policy: cap per-order notional.
        self.max_order_notional: float = _clamp_float(os.getenv("IQS_MAX_ORDER_NOTIONAL", "2000"), default=2000.0)

    def check_trade(self, ticker: str) -> dict[str, Any]:
        """
        Return a dict with at least:
        - signal: "BUY" | "DON'T BUY"
        - quantity: float
        - entry_price: float
        - take_profit: float (optional)
        - stop_loss: float (optional)
        """
        fn = _STRATEGIES.get(self.strategy_name)
        if fn is None:
            raise RuntimeError(f"Unknown strategy: {self.strategy_name!r}. Available: {sorted(_STRATEGIES)}")

        df = _download_ohlcv(ticker, period=self.yf_period, interval=self.yf_interval)
        if df.empty:
            return {"signal": "DON'T BUY"}

        decision = dict(fn(df, self.strategy_params))
        if decision.get("signal") != "BUY":
            return {"signal": "DON'T BUY"}

        px = float(decision.get("entry_price", float(df.iloc[-1]["close"])))
        if px <= 0.0:
            return {"signal": "DON'T BUY"}
        qty = math.floor(self.max_order_notional / px)
        if qty <= 0:
            return {"signal": "DON'T BUY"}

        decision["quantity"] = float(qty)
        decision["entry_price"] = float(px)
        decision["signal"] = "BUY"
        return decision

    def check_sell(self, ticker: str) -> dict[str, Any]:
        """
        Return a dict with at least:
        - signal: "SELL" | "DON'T SELL"
        - quantity: float
        - entry_price: float
        """
        fn = _STRATEGIES.get(self.strategy_name)
        if fn is None:
            raise RuntimeError(f"Unknown strategy: {self.strategy_name!r}. Available: {sorted(_STRATEGIES)}")

        df = _download_ohlcv(ticker, period=self.yf_period, interval=self.yf_interval)
        if df.empty:
            return {"signal": "DON'T SELL"}

        decision = dict(fn(df, self.strategy_params))
        if decision.get("signal") != "SELL":
            return {"signal": "DON'T SELL"}

        px = float(decision.get("entry_price", float(df.iloc[-1]["close"])))
        if px <= 0.0:
            return {"signal": "DON'T SELL"}

        return {"signal": "SELL", "quantity": float(decision.get("quantity", 1.0)), "entry_price": float(px)}


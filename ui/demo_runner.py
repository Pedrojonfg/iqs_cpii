from __future__ import annotations

import sys
import argparse
import asyncio
import datetime as dt
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# Allow `import iqs` without installing the package (same pattern as tests/conftest.py).
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from iqs.app.manager import Manager
from iqs.data.instruments import Instrument
from iqs.data.market_data_feed import FeedConfig, MarketDataFeed
from iqs.strategy.events import VolumeBar
from iqs.strategy.hotpath import HotPathParams
from iqs.strategy.technical import EventDrivenTechnicalAnalyzer


UI_DIR = Path("ui")
STATE_PATH = UI_DIR / "ui_state.json"
LOG_PATH = UI_DIR / "ui_logs.txt"
CAL_DIR = Path("data/calibration")
CAL_LATEST = CAL_DIR / "calibration_latest.json"

LOCAL_TZ = ZoneInfo(os.getenv("IQS_DEMO_TZ", "Europe/Madrid"))

def _now_local_iso() -> str:
    return dt.datetime.now(LOCAL_TZ).isoformat()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_state(payload: dict[str, Any]) -> None:
    _ensure_dir(UI_DIR)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)


def _append_log(line: str) -> None:
    _ensure_dir(UI_DIR)
    LOG_PATH.write_text("", encoding="utf-8") if not LOG_PATH.exists() else None
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _log(component: str, message: str) -> None:
    _append_log(f"[{_now_local_iso()}] [{component}] {message}")


class _FundamentalLike(Protocol):
    def check_trade(self, ticker: str) -> str: ...
    async def check_trade_safe(self, ticker: str) -> str: ...


class AlwaysClearFundamental:
    def check_trade(self, ticker: str) -> str:
        return "CLEAR"

    async def check_trade_safe(self, ticker: str) -> str:
        return "CLEAR"


class DidacticFundamentalAnalyzer:
    """Didactic fundamental veto that really calls NewsFetcher + LLMCheck (Groq)."""

    def __init__(self, *, override_veto_for_demo: bool = True) -> None:
        # Import locally so the module still imports cleanly even if optional deps are missing.
        from iqs.services.news import NewsFetcher
        from iqs.services.nlp_veto import LLMCheck

        self.news = NewsFetcher()
        self.llm = LLMCheck()
        self.override_veto_for_demo = bool(override_veto_for_demo)

    def check_trade(self, ticker: str) -> str:
        # Keep a sync variant for completeness (Manager prefers async safe if available).
        _log("FundamentalAnalyzer.check_trade", f"Fetching recent headlines via NewsFetcher for ticker={ticker!r}")
        t0 = time.time()
        news_xml = self.news.newsfetcher(ticker)
        _log(
            "NewsFetcher.newsfetcher",
            f"Fetched & sanitized headlines in {(time.time() - t0) * 1000:.0f}ms (payload_chars={len(news_xml)})",
        )

        _log("LLMCheck.decide", "Calling Groq LLM for veto decision (JSON-only)")
        t1 = time.time()
        decision = self.llm.decide(ticker, news_xml)
        _log("LLMCheck.decide", f"LLM responded in {(time.time() - t1) * 1000:.0f}ms → decision={decision!r}")

        if decision != "CLEAR" and self.override_veto_for_demo:
            _log(
                "FundamentalAnalyzer",
                "LLM returned VETO. Demo override is enabled → continuing as CLEAR to complete the BUY→SELL walkthrough.",
            )
            return "CLEAR"
        return decision

    async def check_trade_safe(self, ticker: str) -> str:
        _log("FundamentalAnalyzer.check_trade_safe", f"Fetching recent headlines via NewsFetcher (async) for ticker={ticker!r}")
        t0 = time.time()
        news_xml = await self.news.newsfetcher_safe(ticker)
        _log(
            "NewsFetcher.newsfetcher_safe",
            f"Fetched & sanitized headlines in {(time.time() - t0) * 1000:.0f}ms (payload_chars={len(news_xml)})",
        )

        _log("LLMCheck.decide_safe_async", "Calling Groq LLM (async wrapper) for veto decision (JSON-only)")
        t1 = time.time()
        decision = await self.llm.decide_safe_async(ticker, news_xml)
        _log(
            "LLMCheck.decide_safe_async",
            f"LLM responded in {(time.time() - t1) * 1000:.0f}ms → decision={decision!r}",
        )

        if decision != "CLEAR" and self.override_veto_for_demo:
            _log(
                "FundamentalAnalyzer",
                "LLM returned VETO. Demo override is enabled → continuing as CLEAR to complete the BUY→SELL walkthrough.",
            )
            return "CLEAR"
        return decision


class DidacticTechnicalAnalyzer:
    """Wrapper that narrates the technical decision on each VolumeBar."""

    def __init__(self, inner: EventDrivenTechnicalAnalyzer) -> None:
        self.inner = inner

    def on_volume_bar(self, bar: VolumeBar) -> dict[str, Any]:
        _log(
            "EventDrivenTechnicalAnalyzer.on_volume_bar",
            f"Analyzing VolumeBar(symbol={bar.symbol!r}, close={bar.close:.4f}, volume={bar.volume:.0f})",
        )
        decision = self.inner.on_volume_bar(bar)
        _log("EventDrivenTechnicalAnalyzer.on_volume_bar", f"Technical decision={decision}")
        return decision


class FakeExecution:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []

    def send_order(
        self,
        instrument: Instrument | str,
        action: str,
        quantity: float,
        entry_price: float,
        disp_money: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> None:
        sym = instrument.symbol if isinstance(instrument, Instrument) else str(instrument)
        _log(
            "ExecutionHandler.send_order",
            f"Preparing order (SIMULATED): action={action!r} symbol={sym!r} quantity={quantity} entry_price={entry_price}",
        )
        order = {
            "ts_local": _now_local_iso(),
            "symbol": sym,
            "action": str(action),
            "quantity": float(quantity),
            "entry_price": float(entry_price),
            "take_profit": float(take_profit),
            "stop_loss": float(stop_loss),
        }
        self.orders.append(order)
        _log(
            "ExecutionHandler.send_order",
            f"Order accepted (SIMULATED): {order['action']} {order['symbol']} "
            f"qty={order['quantity']:.4g} limit_px={order['entry_price']:.4f} "
            f"take_profit={order['take_profit']:.4f} stop_loss={order['stop_loss']:.4f}",
        )


class FakeBroker:
    """Implements the minimum interface needed by MarketDataFeed + Manager."""

    def __init__(self, *, funds_eur: float = 100_000.0) -> None:
        self.callbacks: list[Any] = []
        self._funds_eur = float(funds_eur)

    def subscribe_to_data(self, instrument: Instrument | str, callback_function: Any) -> None:
        self.callbacks.append(callback_function)

    def get_active_positions(self) -> list[str]:
        return []

    def get_position_market_value(self, symbol: str) -> float:
        return 0.0

    def get_disp_money(self, currency: str = "EUR") -> float:
        return self._funds_eur if currency == "EUR" else 0.0


@dataclass(frozen=True, slots=True)
class _SynthTick:
    time: dt.datetime
    price: float
    size: float


def _make_synth_ticks(*, symbol: str, days_back: int, n: int = 20000) -> list[_SynthTick]:
    # Produce a mildly trending random-walk with random sizes.
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=int(days_back))
    span_s = max(1.0, (now - start).total_seconds())

    px = 100.0
    out: list[_SynthTick] = []
    for i in range(int(n)):
        frac = i / max(1, n - 1)
        t = start + dt.timedelta(seconds=frac * span_s)
        px *= 1.0 + random.uniform(-0.0007, 0.0010)
        size = random.uniform(50.0, 800.0)
        out.append(_SynthTick(time=t, price=float(px), size=float(size)))
    return out


def _synthetic_calibrate_bucket_volume(ticks: list[_SynthTick]) -> float:
    """
    Coldpath-like calibration without IB:
    choose a bucket size that minimizes Jarque–Bera statistic on log-returns
    of the resulting volume bars.
    """
    import math

    import numpy as np
    import pandas as pd

    try:
        from scipy.stats import jarque_bera as scipy_jb  # type: ignore
    except Exception:  # pragma: no cover
        scipy_jb = None

    if not ticks:
        return 5000.0

    df = pd.DataFrame(
        {
            "time": [t.time for t in ticks],
            "price": [float(t.price) for t in ticks],
            "size": [float(t.size) for t in ticks],
        }
    )
    df = df.dropna()
    if df.empty:
        return 5000.0

    df["cumsize"] = df["size"].cumsum()
    candle_sizes = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
    best_jb = float("inf")
    best_candle = 5000.0

    _log(
        "DataCalibrator.calibrate_with_jarque_bera",
        f"Running Jarque–Bera normality test across candidate bucket sizes: {candle_sizes}",
    )

    for c in candle_sizes:
        df["ID"] = (df["cumsize"] // float(c)).astype("int64", errors="ignore")
        candles = df.groupby("ID").agg(close=("price", "last"))
        if len(candles) < 30:
            _log(
                "DataCalibrator.calibrate_with_jarque_bera",
                f"bucket={c:>6}: skipped (not enough volume-bars: n={len(candles)} < 30)",
            )
            continue
        close = candles["close"].to_numpy(dtype=float)
        if close.size < 2:
            continue
        r = np.log(close[1:] / close[:-1])
        r = r[np.isfinite(r)]
        if r.size < 20:
            _log(
                "DataCalibrator.calibrate_with_jarque_bera",
                f"bucket={c:>6}: skipped (not enough returns after cleaning: n={r.size} < 20)",
            )
            continue

        if scipy_jb is not None:
            jb_stat, _p = scipy_jb(r)
            score = float(jb_stat)
        else:
            # Fallback: use moment-based JB approximation (not exact p-values).
            n = float(r.size)
            mu = float(r.mean())
            s2 = float(((r - mu) ** 2).mean())
            if s2 <= 0:
                continue
            s = float(((r - mu) ** 3).mean()) / (s2 ** 1.5)
            k = float(((r - mu) ** 4).mean()) / (s2 * s2)
            score = (n / 6.0) * (s * s + 0.25 * ((k - 3.0) ** 2))
        if not math.isfinite(score):
            continue
        _log("DataCalibrator.calibrate_with_jarque_bera", f"bucket={c:>6}: JB_stat={score:.3f}")
        if score < best_jb:
            best_jb = score
            best_candle = float(c)

    _log(
        "DataCalibrator.calibrate_with_jarque_bera",
        f"Selected best bucket_volume={best_candle:.0f} (min JB_stat={best_jb:.3f})",
    )
    return float(best_candle)


def run_coldpath(*, mode: str, symbol: str, days_back: int) -> float:
    _log("ColdPathRunner.run", f"Fetching past data to calibrate volume candles (mode={mode}, symbol={symbol}, lookback_days={days_back})")
    if mode == "synthetic":
        _log("ColdPathRunner.run", "Generating SYNTHETIC tick data (price, size, timestamp)")
        ticks = _make_synth_ticks(symbol=symbol, days_back=days_back)
        _log("ColdPathRunner.run", f"Generated n_ticks={len(ticks)}. Passing to DataCalibrator.")
        bucket = float(_synthetic_calibrate_bucket_volume(ticks))
    else:
        load_dotenv()
        from ib_insync import IB

        from iqs.coldpath.calibrator import DataCalibrator
        from iqs.data.broker import BrokerData

        ib_host = os.getenv("IB_HOST", "127.0.0.1").strip()
        ib_port = int(os.getenv("IB_PORT", "7497").strip())
        ib_client_id = int(os.getenv("IB_CLIENT_ID", "1").strip())

        _log("ColdPathRunner.run", f"Connecting to Interactive Brokers (IB={ib_host}:{ib_port}, client_id={ib_client_id})")
        ib = IB()
        ib.connect(ib_host, ib_port, clientId=ib_client_id)
        try:
            broker = BrokerData(ib)
            calibrator = DataCalibrator(broker)
            bucket = float(calibrator.coldpath(symbol, days_back=days_back))
        finally:
            ib.disconnect()

    _ensure_dir(CAL_DIR)
    payload = {
        "generated_at_local": _now_local_iso(),
        "days_back": int(days_back),
        "bucket_volume_by_symbol": {symbol: float(bucket)},
    }
    tmp = CAL_LATEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(CAL_LATEST)
    _log("ColdPathRunner.run", f"Volume candles calibrated → bucket_volume={bucket:.0f}. Starting Hot Path next.")
    _log("ColdPathRunner.run", f"Calibration saved to {CAL_LATEST.as_posix()}")
    return float(bucket)


async def _hotpath_loop_synth(*, symbol: str, seconds: float, bucket_volume: float) -> None:
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[VolumeBar] = asyncio.Queue(maxsize=2000)

    broker = FakeBroker()
    ins = [Instrument(symbol=symbol, exchange="SMART", currency="EUR")]
    _log("MarketDataFeed.__init__", f"Building MarketDataFeed for {len(ins)} instrument(s): {[i.symbol for i in ins]}")
    feed = MarketDataFeed(
        broker=broker,
        instruments=ins,
        out_queue=q,
        loop=loop,
        config=FeedConfig(default_bucket_volume=float(bucket_volume), calibration_path="__missing__.json"),
    )
    _log("MarketDataFeed.start", "Subscribing to tick stream(s) via Broker.subscribe_to_data(...)")
    feed.start()
    if not broker.callbacks:
        raise RuntimeError("Synthetic broker produced no callbacks")
    cb = broker.callbacks[0]

    fundamental: _FundamentalLike = DidacticFundamentalAnalyzer()
    execution = FakeExecution()

    # Demo-friendly params: warm up quickly and trigger signals with modest moves.
    hot_params = HotPathParams(window_bars=128, min_bars=20, vol_window=20, band_k=1.0, trailing_k=2.0)
    _log("HotPathParams", f"Configured HotPathParams={hot_params}")
    technical = DidacticTechnicalAnalyzer(EventDrivenTechnicalAnalyzer(hot_params=hot_params))
    manager = Manager(
        broker=broker,
        tickers=ins,
        fundamental_analyzer=fundamental,
        technical_analyzer=technical,
        execution_handler=execution,
    )

    _log(
        "iqs.app.manager.Manager",
        "Hot Path: entering event-driven loop: ticks → MarketDataFeed → VolumeBar → TechnicalAnalyzer → FundamentalAnalyzer → ExecutionHandler",
    )
    _log("HotPathConfig", f"Using bucket_volume={bucket_volume:.0f} for symbol={symbol}")
    _write_state(
        {
            "connection_status": "SYNTHETIC",
            "symbol": symbol,
            "last_price": None,
            "signal": "WAITING",
            "position_state": "SIM",
            "last_event_time": _now_local_iso(),
            "last_error": None,
        }
    )

    px = 100.0
    t_end = time.time() + float(seconds)
    last_ui_ts = 0.0
    bar_count = 0
    forced_breakout = False
    forced_crash = False
    saw_buy = False
    saw_sell = False
    last_stop_loss: float | None = None

    while time.time() < t_end:
        # Slight drift and occasional impulse to trigger breakouts.
        shock = 1.0
        # After enough warmup bars, force a clear breakout once to guarantee a BUY.
        if (not forced_breakout) and bar_count >= int(hot_params.min_bars) + 5:
            shock = 1.0 + 0.04  # strong impulse
            forced_breakout = True
            _log("SyntheticMarket", "Injecting bullish shock to force a BUY breakout (didactic demo)")
        else:
            if random.random() < 0.0005:
                shock = 1.0 + random.uniform(0.002, 0.008)
        px *= (1.0 + random.uniform(-0.0004, 0.0005)) * shock
        # Clamp for demo stability (avoid insane compounding when loop runs fast).
        if px < 1.0:
            px = 1.0
        elif px > 500.0:
            px = 500.0

        # After we see a BUY (and have a stop_loss), force the next bars to trade below the stop
        # to guarantee a SELL/EXIT via trailing stop.
        if saw_buy and (not saw_sell) and (last_stop_loss is not None) and (not forced_crash):
            px = max(1.0, float(last_stop_loss) * 0.97)
            forced_crash = True
            _log("SyntheticMarket", "Forcing price below trailing stop to guarantee a SELL/EXIT (didactic demo)")

        size = random.uniform(100.0, 1200.0)
        cb(price=float(px), size=float(size), timestamp=time.time())
        await asyncio.sleep(0.01)  # throttle: keeps logs/UI readable

        drained = 0
        while not q.empty():
            bar = await q.get()
            drained += 1
            bar_count += 1
            _log(
                "MarketDataFeed",
                f"Emitted VolumeBar(symbol={bar.symbol!r}, O={bar.open:.4f}, H={bar.high:.4f}, "
                f"L={bar.low:.4f}, C={bar.close:.4f}, V={bar.volume:.0f})",
            )

            before_orders = len(execution.orders)
            await manager.on_volume_bar(bar)
            after_orders = len(execution.orders)

            if after_orders > before_orders:
                last = execution.orders[-1]
                action = str(last.get("action", ""))
                if action.upper() == "BUY":
                    saw_buy = True
                    last_stop_loss = float(last.get("stop_loss", 0.0)) or None
                    _log(
                        "DemoOrchestrator",
                        f"Observed BUY execution. Captured stop_loss={last_stop_loss} for guaranteed SELL step.",
                    )
                elif action.upper() == "SELL":
                    saw_sell = True
                    _log("DemoOrchestrator", "Observed SELL execution. End-to-end cycle complete (BUY → SELL).")

            # Update UI state (not for every tick; for each bar is fine).
            _write_state(
                {
                    "connection_status": "SYNTHETIC",
                    "symbol": bar.symbol,
                    "last_price": float(bar.close),
                    "signal": ("SELL" if saw_sell else ("BUY" if saw_buy else "RUNNING")),
                    "position_state": "SIM",
                    "last_event_time": _now_local_iso(),
                    "last_error": None,
                }
            )

            if saw_buy and saw_sell:
                # End early once we have a guaranteed full demo cycle.
                t_end = min(t_end, time.time() + 0.25)
                break

        # keep UI timestamp fresh even if bars are slow
        if time.time() - last_ui_ts > 2.0 and drained == 0:
            last_ui_ts = time.time()
            _write_state(
                {
                    "connection_status": "SYNTHETIC",
                    "symbol": symbol,
                    "last_price": float(px),
                    "signal": "WAITING_BAR",
                    "position_state": "SIM",
                    "last_event_time": _now_local_iso(),
                    "last_error": None,
                }
            )

    _log("HotPathRunner", "Demo finished (no real orders were sent)")


def main() -> None:
    parser = argparse.ArgumentParser(description="IQS UI demo runner (cold path + hot path) for local demos.")
    parser.add_argument("--mode", choices=["synthetic", "ib"], default="synthetic")
    parser.add_argument("--symbol", default="AAA")
    parser.add_argument("--days-back", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--bucket-volume", type=float, default=0.0, help="If 0, uses coldpath output or fallback.")
    parser.add_argument("--run-coldpath", action="store_true")
    parser.add_argument("--run-hotpath", action="store_true")
    args = parser.parse_args()

    # Load .env early so GROQ_API_KEY/IB_* are available for the demo.
    load_dotenv()

    # Reset state/logs for a clean demo.
    _ensure_dir(UI_DIR)
    LOG_PATH.write_text("", encoding="utf-8")
    _write_state(
        {
            "connection_status": "BOOT",
            "symbol": args.symbol,
            "last_price": None,
            "signal": "DON'T BUY",
            "position_state": "CLOSED",
            "last_event_time": _now_local_iso(),
            "last_error": None,
        }
    )

    try:
        bucket = float(args.bucket_volume)
        if args.run_coldpath or bucket <= 0.0:
            bucket = run_coldpath(mode=args.mode, symbol=str(args.symbol), days_back=int(args.days_back))
        # Demo guardrail: keep bucket large enough to avoid log floods.
        if args.mode == "synthetic" and bucket < 5000.0:
            bucket = 5000.0
        if not args.run_hotpath:
            _log("DemoRunner", "Done (cold path only).")
            return
        if args.mode != "synthetic":
            raise SystemExit("Hot path demo is currently implemented only in synthetic mode (no IB).")
        asyncio.run(_hotpath_loop_synth(symbol=str(args.symbol), seconds=float(args.seconds), bucket_volume=float(bucket)))
    except Exception as e:
        _log("DemoRunner", f"ERROR {type(e).__name__}: {e}")
        _write_state(
            {
                "connection_status": "ERROR",
                "symbol": args.symbol,
                "last_price": None,
                "signal": "DON'T BUY",
                "position_state": "CLOSED",
                "last_event_time": _now_local_iso(),
                "last_error": f"{type(e).__name__}: {e}",
            }
        )
        raise


if __name__ == "__main__":
    main()


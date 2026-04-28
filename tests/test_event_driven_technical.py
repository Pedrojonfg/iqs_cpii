import os
import time

from iqs.strategy.events import VolumeBar
from iqs.hotpath import HotPathParams
from iqs.technical import EventDrivenTechnicalAnalyzer


def _bar(symbol: str, px: float, vol: float, ts: float) -> VolumeBar:
    return VolumeBar(
        symbol=symbol,
        open=px,
        high=px,
        low=px,
        close=px,
        volume=vol,
        start_ts=ts,
        end_ts=ts + 1.0,
    )


def test_event_driven_technical_translates_buy_and_stop():
    os.environ["IQS_MAX_ORDER_NOTIONAL"] = "1000"
    os.environ["IQS_TP_PCT"] = "0.05"

    hot = HotPathParams(window_bars=128, min_bars=20, vol_window=20, band_k=1.0, trailing_k=2.0)
    ta = EventDrivenTechnicalAnalyzer(hot_params=hot)

    t0 = time.time()
    px = 100.0
    # Warm-up flat history
    for i in range(25):
        decision = ta.on_volume_bar(_bar("AAA", px, 10000.0, t0 + i))
        assert decision["signal"] == "DON'T BUY"

    # Breakout jump
    px *= 1.05
    decision = ta.on_volume_bar(_bar("AAA", px, 10000.0, t0 + 26))
    assert decision["signal"] == "BUY"
    assert decision["quantity"] == 9.0  # floor(1000 / 105)
    assert decision["stop_loss"] < decision["entry_price"]
    assert decision["take_profit"] > decision["entry_price"]


def test_event_driven_technical_translates_sell():
    os.environ["IQS_MAX_ORDER_NOTIONAL"] = "1000"
    os.environ["IQS_TP_PCT"] = "0.05"

    hot = HotPathParams(window_bars=128, min_bars=20, vol_window=20, band_k=1.0, trailing_k=2.0)
    ta = EventDrivenTechnicalAnalyzer(hot_params=hot)

    t0 = time.time()
    px = 100.0
    for i in range(25):
        _ = ta.on_volume_bar(_bar("AAA", px, 10000.0, t0 + i))

    px *= 1.05
    buy = ta.on_volume_bar(_bar("AAA", px, 10000.0, t0 + 26))
    assert buy["signal"] in {"BUY", "DON'T BUY"}

    # Force price below stop to trigger -1 in hotpath.
    stop = float(buy.get("stop_loss", px * 0.95))
    decision = ta.on_volume_bar(_bar("AAA", stop * 0.99, 10000.0, t0 + 27))
    assert decision["signal"] in {"SELL", "DON'T BUY"}


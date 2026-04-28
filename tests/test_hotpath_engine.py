import time

from iqs.strategy.events import VolumeBar
from iqs.hotpath import HotPathEngine, HotPathParams


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


def test_hotpath_warmup_returns_noop():
    hp = HotPathEngine(HotPathParams(window_bars=64, min_bars=10, vol_window=10, band_k=2.0, trailing_k=3.0))
    t0 = time.time()
    for i in range(9):
        res = hp.update(_bar("AAA", 100.0 + i, 10000.0, t0 + i))
        assert res.signal == 0


def test_hotpath_breakout_buy_then_trailing_exit():
    hp = HotPathEngine(HotPathParams(window_bars=128, min_bars=20, vol_window=20, band_k=1.0, trailing_k=2.0))
    t0 = time.time()

    # Flat-ish series to build history without triggering a breakout.
    px = 100.0
    for i in range(25):
        res = hp.update(_bar("AAA", px, 10000.0, t0 + i))

    # Big jump to force breakout -> BUY
    px *= 1.05
    res = hp.update(_bar("AAA", px, 10000.0, t0 + 26))
    assert res.signal == 1
    assert res.trailing_stop == res.trailing_stop  # not NaN

    # Drop below trailing stop -> should force EXIT (-1)
    px = res.trailing_stop * 0.99
    res2 = hp.update(_bar("AAA", px, 10000.0, t0 + 27))
    assert res2.signal == -1


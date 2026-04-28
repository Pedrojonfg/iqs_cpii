from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VolumeBar:
    """
    Event emitted by the MarketDataFeed when a volume bucket completes.

    This is the *only* thing the hot path needs to see: a compact OHLCV snapshot.
    """

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_ts: float  # epoch seconds (float for sub-second precision)
    end_ts: float


@dataclass(frozen=True, slots=True)
class HotPathResult:
    """
    Output of the hot path evaluation for a symbol at the close of a bar.
    """

    symbol: str
    signal: int  # +1 BUY, 0 NOOP, -1 SELL/EXIT
    ref_price: float
    vwap: float
    upper: float
    lower: float
    sigma: float
    trailing_stop: float


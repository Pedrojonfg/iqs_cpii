from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VolumeBar:
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    start_ts: float
    end_ts: float


@dataclass(frozen=True, slots=True)
class HotPathResult:
    symbol: str
    signal: int  # +1 BUY, 0 NOOP, -1 SELL/EXIT
    ref_price: float
    vwap: float
    upper: float
    lower: float
    sigma: float
    trailing_stop: float


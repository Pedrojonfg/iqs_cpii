from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Instrument:
    """Minimal IB instrument definition used to build broker contracts."""

    symbol: str
    exchange: str
    currency: str

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from iqs.data.instruments import Instrument
from iqs.strategy.events import VolumeBar


@dataclass(frozen=True, slots=True)
class FeedConfig:
    default_bucket_volume: float = 10_000.0
    calibration_path: str = "data/calibration/calibration_latest.json"


class _BrokerLike:
    def subscribe_to_data(self, instrument: Instrument | str, callback_function: Callable[..., Any]) -> None: ...


class MarketDataFeed:
    def __init__(
        self,
        *,
        broker: _BrokerLike,
        instruments: list[Instrument],
        out_queue: "asyncio.Queue[VolumeBar]",
        loop: asyncio.AbstractEventLoop,
        config: FeedConfig | None = None,
    ) -> None:
        self.broker = broker
        self.instruments = instruments
        self.out_queue = out_queue
        self.loop = loop
        self.config = config or FeedConfig()

        self.bucket_volume_by_symbol: dict[str, float] = self._load_bucket_volumes(self.config.calibration_path)
        self._state: dict[str, dict[str, float]] = {}

    @staticmethod
    def _load_bucket_volumes(path: str) -> dict[str, float]:
        p = Path(path)
        if not p.exists():
            return {}
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            raw = payload.get("bucket_volume_by_symbol", {}) or {}
            out: dict[str, float] = {}
            for k, v in raw.items():
                try:
                    fv = float(v)
                except Exception:
                    continue
                if fv > 0:
                    out[str(k)] = fv
            return out
        except Exception:
            return {}

    def _bucket_volume(self, symbol: str) -> float:
        return float(self.bucket_volume_by_symbol.get(symbol, self.config.default_bucket_volume))

    def start(self) -> None:
        for ins in self.instruments:
            self.broker.subscribe_to_data(ins, self._make_tick_callback(ins))

    def _make_tick_callback(self, instrument: Instrument) -> Callable[..., Any]:
        symbol = instrument.symbol

        def _cb(*args: Any, **kwargs: Any) -> None:
            tick = args[0] if args else None
            price = None
            size = None
            ts = None

            if tick is not None:
                for attr in ("price", "last", "lastPrice"):
                    if hasattr(tick, attr):
                        try:
                            price = float(getattr(tick, attr))
                            break
                        except Exception:
                            pass
                for attr in ("size", "lastSize"):
                    if hasattr(tick, attr):
                        try:
                            size = float(getattr(tick, attr))
                            break
                        except Exception:
                            pass
                for attr in ("time", "timestamp"):
                    if hasattr(tick, attr):
                        try:
                            tsv = getattr(tick, attr)
                            ts = float(tsv.timestamp()) if hasattr(tsv, "timestamp") else float(tsv)
                            break
                        except Exception:
                            pass

            if price is None:
                for key in ("price", "last", "lastPrice"):
                    if key in kwargs:
                        try:
                            price = float(kwargs[key])
                            break
                        except Exception:
                            pass
            if size is None:
                for key in ("size", "lastSize"):
                    if key in kwargs:
                        try:
                            size = float(kwargs[key])
                            break
                        except Exception:
                            pass

            if ts is None:
                ts = time.time()

            if price is None or size is None or price <= 0.0 or size <= 0.0:
                return

            self._on_tick(symbol=symbol, price=float(price), size=float(size), ts=float(ts))

        return _cb

    def _on_tick(self, *, symbol: str, price: float, size: float, ts: float) -> None:
        st = self._state.get(symbol)
        if st is None:
            st = {
                "cum_vol": 0.0,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "start_ts": ts,
                "end_ts": ts,
            }
            self._state[symbol] = st

        st["cum_vol"] += size
        st["close"] = price
        st["end_ts"] = ts
        if price > st["high"]:
            st["high"] = price
        if price < st["low"]:
            st["low"] = price

        bucket = self._bucket_volume(symbol)
        if st["cum_vol"] < bucket:
            return

        bar = VolumeBar(
            symbol=symbol,
            open=float(st["open"]),
            high=float(st["high"]),
            low=float(st["low"]),
            close=float(st["close"]),
            volume=float(st["cum_vol"]),
            start_ts=float(st["start_ts"]),
            end_ts=float(st["end_ts"]),
        )

        self._state[symbol] = {
            "cum_vol": 0.0,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "start_ts": ts,
            "end_ts": ts,
        }

        self.loop.call_soon_threadsafe(self.out_queue.put_nowait, bar)


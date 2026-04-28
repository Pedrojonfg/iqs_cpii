from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from iqs.strategy.events import HotPathResult, VolumeBar
from iqs.strategy.math_engine import hotpath_vwap_bands_signal


@dataclass
class HotPathParams:
    window_bars: int = 256
    min_bars: int = 60
    vol_window: int = 60
    band_k: float = 2.0
    trailing_k: float = 3.0


@dataclass
class _SymbolState:
    closes: list[float]
    volumes: list[float]
    trailing_stop: float
    in_position: bool


class HotPathEngine:
    def __init__(self, params: HotPathParams | None = None) -> None:
        self.params = params or HotPathParams()
        self._state: dict[str, _SymbolState] = {}

    def _get_state(self, symbol: str) -> _SymbolState:
        st = self._state.get(symbol)
        if st is None:
            st = _SymbolState(closes=[], volumes=[], trailing_stop=float("nan"), in_position=False)
            self._state[symbol] = st
        return st

    def update(self, bar: VolumeBar) -> HotPathResult:
        st = self._get_state(bar.symbol)
        st.closes.append(float(bar.close))
        st.volumes.append(float(bar.volume))

        if len(st.closes) > self.params.window_bars:
            overflow = len(st.closes) - self.params.window_bars
            if overflow > 0:
                del st.closes[:overflow]
                del st.volumes[:overflow]

        n = len(st.closes)
        ref_price = float(st.closes[-1]) if n else float("nan")

        if n < self.params.min_bars:
            return HotPathResult(
                symbol=bar.symbol,
                signal=0,
                ref_price=ref_price,
                vwap=float("nan"),
                upper=float("nan"),
                lower=float("nan"),
                sigma=float("nan"),
                trailing_stop=st.trailing_stop,
            )

        closes = np.asarray(st.closes, dtype=np.float64)
        volumes = np.asarray(st.volumes, dtype=np.float64)

        signal, vw, upper, lower, sigma = hotpath_vwap_bands_signal(
            closes,
            volumes,
            vol_window=int(self.params.vol_window),
            band_k=float(self.params.band_k),
        )

        if st.in_position and signal == 1:
            signal = 0

        if np.isfinite(sigma) and np.isfinite(ref_price) and ref_price > 0.0:
            trail_dist = float(self.params.trailing_k) * float(sigma) * ref_price
        else:
            trail_dist = float("nan")

        if signal == 1:
            st.in_position = True
            if np.isfinite(trail_dist):
                st.trailing_stop = ref_price - trail_dist

        if st.in_position and np.isfinite(trail_dist):
            candidate = ref_price - trail_dist
            if not np.isfinite(st.trailing_stop):
                st.trailing_stop = candidate
            else:
                st.trailing_stop = max(st.trailing_stop, candidate)

        if st.in_position and np.isfinite(st.trailing_stop) and ref_price <= st.trailing_stop:
            signal = -1
            st.in_position = False

        return HotPathResult(
            symbol=bar.symbol,
            signal=int(signal),
            ref_price=ref_price,
            vwap=float(vw),
            upper=float(upper),
            lower=float(lower),
            sigma=float(sigma),
            trailing_stop=float(st.trailing_stop),
        )

    def snapshot_state(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for sym, st in self._state.items():
            out[sym] = {
                "bars": len(st.closes),
                "in_position": bool(st.in_position),
                "trailing_stop": st.trailing_stop,
                "last_close": st.closes[-1] if st.closes else None,
            }
        return out


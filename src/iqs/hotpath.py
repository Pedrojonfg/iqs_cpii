from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from iqs.events import HotPathResult, VolumeBar
from iqs.math_engine import hotpath_vwap_bands_signal


@dataclass
class HotPathParams:
    """
    Parameters for the hot path engine.

    Keep these simple and explicit so you can reason about them in production.
    """

    window_bars: int = 256          # how many bars to keep in memory per symbol
    min_bars: int = 60              # warm-up before we allow any signal
    vol_window: int = 60            # how many returns to estimate sigma
    band_k: float = 2.0             # band width multiplier
    trailing_k: float = 3.0         # trailing stop multiplier (in return-vol * price units)


@dataclass
class _SymbolState:
    closes: list[float]
    volumes: list[float]
    trailing_stop: float
    in_position: bool


class HotPathEngine:
    """
    Stateful hot path engine.

    ELI5:
    - It keeps a small notebook of the last N bar closes/volumes per symbol.
    - Every time a new bar arrives, it updates the notebook.
    - Then it calls a Numba-accelerated function to get VWAP + bands + signal.
    - It also maintains a trailing stop (simple, dynamic, volatility-based).

    NOTE: This is the "max readability" implementation:
    - It stores history in Python lists.
    - On each bar, it converts the last window to numpy arrays for Numba.
    That's totally fine for mid-frequency bars; later we can switch to ring buffers.
    """

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
        """
        Ingest a completed volume bar and return the hot path evaluation result.
        """
        st = self._get_state(bar.symbol)

        # 1) Append new data
        st.closes.append(float(bar.close))
        st.volumes.append(float(bar.volume))

        # 2) Enforce fixed memory
        if len(st.closes) > self.params.window_bars:
            overflow = len(st.closes) - self.params.window_bars
            if overflow > 0:
                del st.closes[:overflow]
                del st.volumes[:overflow]

        n = len(st.closes)
        ref_price = float(st.closes[-1]) if n else float("nan")

        # 3) Warm-up
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

        # 4) Build numpy arrays (contiguous) for Numba
        closes = np.asarray(st.closes, dtype=np.float64)
        volumes = np.asarray(st.volumes, dtype=np.float64)

        # 5) Evaluate VWAP bands + signal (Numba)
        signal, vw, upper, lower, sigma = hotpath_vwap_bands_signal(
            closes,
            volumes,
            vol_window=int(self.params.vol_window),
            band_k=float(self.params.band_k),
        )

        # If we're already in a position, a new BUY signal is not actionable.
        # We treat it as NOOP and keep managing the trailing stop.
        if st.in_position and signal == 1:
            signal = 0

        # 6) Trailing stop logic (only meaningful if we treat +1 as "enter long")
        # We express stop distance as trailing_k * sigma_return * price.
        if np.isfinite(sigma) and np.isfinite(ref_price) and ref_price > 0.0:
            trail_dist = float(self.params.trailing_k) * float(sigma) * ref_price
        else:
            trail_dist = float("nan")

        # If we get a BUY signal, we consider ourselves "in position".
        if signal == 1:
            st.in_position = True
            if np.isfinite(trail_dist):
                st.trailing_stop = ref_price - trail_dist

        # If in position, move the stop up (never down).
        if st.in_position and np.isfinite(trail_dist):
            candidate = ref_price - trail_dist
            if not np.isfinite(st.trailing_stop):
                st.trailing_stop = candidate
            else:
                st.trailing_stop = max(st.trailing_stop, candidate)

        # If in position and price hits trailing stop, force an exit signal.
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
        """
        Debug helper: return a JSON-friendly snapshot of internal state.
        """
        out: dict[str, dict[str, Any]] = {}
        for sym, st in self._state.items():
            out[sym] = {
                "bars": len(st.closes),
                "in_position": bool(st.in_position),
                "trailing_stop": st.trailing_stop,
                "last_close": st.closes[-1] if st.closes else None,
            }
        return out


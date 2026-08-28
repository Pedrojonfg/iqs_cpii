from __future__ import annotations

import math
import os
from typing import Any

import numpy as np

from iqs.strategy.events import VolumeBar
from iqs.strategy.hotpath import HotPathEngine, HotPathParams


def _clamp_float(value: Any, *, default: float) -> float:
    try:
        fv = float(value)
    except Exception:
        return default
    return fv


class EventDrivenTechnicalAnalyzer:
    def __init__(self, *, hot_params: HotPathParams | None = None) -> None:
        self.hot: HotPathEngine = HotPathEngine(hot_params)
        self.max_order_notional: float = _clamp_float(os.getenv("IQS_MAX_ORDER_NOTIONAL", "2000"), default=2000.0)
        self.take_profit_pct: float = _clamp_float(os.getenv("IQS_TP_PCT", "0.06"), default=0.06)

    def on_volume_bar(self, bar: VolumeBar) -> dict[str, Any]:
        res = self.hot.update(bar)
        px = float(res.ref_price)
        if not np.isfinite(px) or px <= 0.0:
            return {"signal": "DON'T BUY"}

        if res.signal == 1:
            qty = math.floor(self.max_order_notional / px)
            if qty <= 0:
                return {"signal": "DON'T BUY"}

            stop_loss = float(res.trailing_stop)
            if not np.isfinite(stop_loss) or stop_loss <= 0.0 or stop_loss >= px:
                return {"signal": "DON'T BUY"}

            return {
                "signal": "BUY",
                "quantity": float(qty),
                "entry_price": px,
                "take_profit": px * (1.0 + self.take_profit_pct),
                "stop_loss": stop_loss,
            }

        if res.signal == -1:
            return {"signal": "SELL", "quantity": 1.0, "entry_price": px}

        return {"signal": "DON'T BUY"}

import os

import numpy as np
import pandas as pd


def _make_df_from_close(close: np.ndarray) -> pd.DataFrame:
    # Minimal OHLCV frame compatible with technical._download_ohlcv output
    close = np.asarray(close, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": np.full_like(close, 1.0),
        }
    )


def test_me_simple_v1_trend_up_triggers_buy(monkeypatch):
    from iqs import technical

    os.environ["IQS_STRATEGY"] = "me_simple_v1"
    os.environ["IQS_STRATEGY_PARAMS"] = (
        '{"z_window":20,"entry_z":0.5,"exit_z":-1.0,"hurst_min":0.50,"hurst_max":0.40,"vol_window":120,"vol_cap":0.20,'
        '"take_profit_pct":0.06,"stop_loss_pct":0.03}'
    )

    # Smooth upward drift with low noise
    n = 260
    close = 100.0 + np.cumsum(np.full(n, 0.15))
    # Add a final positive impulse so recent return z-score is meaningfully positive.
    close[-1] = close[-2] * 1.02
    df = _make_df_from_close(close)

    monkeypatch.setattr(technical, "_download_ohlcv", lambda *args, **kwargs: df)
    ta = technical.TechnicalAnalyzer()
    decision = ta.check_trade("FAKE")

    assert decision["signal"] == "BUY"
    assert decision["quantity"] > 0
    assert decision["entry_price"] > 0
    assert decision["take_profit"] > decision["entry_price"]
    assert decision["stop_loss"] < decision["entry_price"]


def test_me_simple_v1_negative_shock_triggers_sell(monkeypatch):
    from iqs import technical

    os.environ["IQS_STRATEGY"] = "me_simple_v1"
    os.environ["IQS_STRATEGY_PARAMS"] = (
        '{"z_window":20,"entry_z":1.0,"exit_z":-0.5,"hurst_min":0.55,"hurst_max":0.45,"vol_window":120,"vol_cap":0.50}'
    )

    n = 260
    close = 100.0 + np.cumsum(np.full(n, 0.05))
    close[-1] = close[-2] * 0.90  # big down move
    df = _make_df_from_close(close)

    monkeypatch.setattr(technical, "_download_ohlcv", lambda *args, **kwargs: df)
    ta = technical.TechnicalAnalyzer()
    decision = ta.check_sell("FAKE")

    assert decision["signal"] == "SELL"
    assert decision["entry_price"] > 0


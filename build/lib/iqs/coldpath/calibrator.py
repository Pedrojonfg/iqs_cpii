from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np
import pandas as pd
from ib_insync import util
from scipy.stats import jarque_bera


class _BrokerLike(Protocol):
    def fetch_past_data(self, symbol: str, days_back: int = 5) -> Sequence[Any]: ...


class DataCalibrator:
    """Calibrate a volume-based candle size using historical tick data."""

    def __init__(self, broker: _BrokerLike) -> None:
        self.broker: _BrokerLike = broker

    def fetch_and_clean_data(self, symbol: str, days_back: int = 5) -> pd.DataFrame:
        raw_data = self.broker.fetch_past_data(symbol, days_back)
        df: pd.DataFrame = util.df(raw_data)
        df = df[["time", "price", "size"]]
        return df

    def calibrate_with_scipy(self, df: pd.DataFrame) -> int:
        df["cumsize"] = df["size"].cumsum()
        candles_sizes: list[int] = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
        best_jb_stat: float = float("inf")
        best_candle_size: int = 5000
        for c in candles_sizes:
            df["ID"] = df["cumsize"] // c
            candles = df.groupby("ID").agg(
                open=("price", "first"),
                high=("price", "max"),
                low=("price", "min"),
                close=("price", "last"),
                volume=("size", "sum"),
            )
            if len(candles) < 30:
                continue
            returns = np.log(candles["close"] / candles["close"].shift(1)).dropna()
            jb_stat, _p_value = jarque_bera(returns)
            if jb_stat < best_jb_stat:
                best_jb_stat = jb_stat
                best_candle_size = c
        return best_candle_size

    def coldpath(self, symbol: str, days_back: int = 5) -> int:
        pastdata = self.fetch_and_clean_data(symbol, days_back)
        return self.calibrate_with_scipy(pastdata)


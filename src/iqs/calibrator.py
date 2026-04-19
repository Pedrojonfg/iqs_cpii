from scipy.stats import jarque_bera
import pandas as pd
import numpy as np
from ib_insync import util

class DataCalibrator:
    def __init__(self, broker):
        self.broker=broker
    def fetch_and_clean_data(self, symbol, days_back=5):
        raw_data=self.broker.fetch_past_data(symbol, days_back)
        df= util.df(raw_data)
        df= df[["time", "price", "size"]]
        return df
    def calibrate_with_scipy(self, df):   
        df["cumsize"]=df["size"].cumsum()
        candles_sizes=[100, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000]
        best_jb_stat= float('inf')
        best_candle_size = 5000
        for c in candles_sizes:
            df["ID"]= df["cumsize"]//c
            candles = df.groupby("ID").agg(
                open=("price", "first"),
                high=("price", "max"),
                low=("price", "min"),
                close=("price", "last"),
                volume=("size", "sum")
            )
            if len(candles)<30:
                continue
            returns = np.log(candles["close"] / candles["close"].shift(1)).dropna()
            jb_stat, p_value = jarque_bera(returns)
            if jb_stat<best_jb_stat:
                best_jb_stat=jb_stat
                best_candle_size=c
        return best_candle_size
    
    def coldpath(self, symbol, days_back=5):
        pastdata= self.fetch_and_clean_data(symbol, days_back)
        return self.calibrate_with_scipy(pastdata)

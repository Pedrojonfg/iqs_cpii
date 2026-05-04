from __future__ import annotations

import datetime
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import pandas as pd

from iqs.data.instruments import Instrument

if TYPE_CHECKING:
    from ib_insync import IB


class BrokerData:
    """Thin wrapper around an Interactive Brokers (`ib_insync`) connection.

    This class centralizes the market/account data access used by the rest of the
    system (positions, available funds, live tick subscriptions, and historical
    tick retrieval).
    """

    def __init__(self, ib_connection: "IB") -> None:
        """Create a broker data adapter.

        Args:
            ib_connection: Connected `ib_insync.IB` instance.
        """
        self.ib: "IB" = ib_connection

    def get_active_positions(self) -> list[str]:
        """Return symbols with a positive open position."""
        positions = self.ib.positions()
        return [pos.contract.symbol for pos in positions if pos.position > 0]

    def get_position_market_value(self, symbol: str) -> float:
        """Return an approximate current position value for `symbol`."""
        for pos in self.ib.positions():
            if pos.contract.symbol == symbol and pos.position > 0:
                return abs(float(pos.position) * float(pos.avgCost))
        return 0.0

    def get_disp_money(self, currency: str = "EUR") -> float:
        """Get available buying power in the requested currency."""
        acc_values = self.ib.accountValues()
        for value in acc_values:
            if value.tag == "AvailableFunds" and value.currency == currency:
                return float(value.value)
        return 0.0

    def _build_stock_contract(self, instrument: Instrument | str):
        from ib_insync import Stock

        if isinstance(instrument, Instrument):
            return Stock(instrument.symbol, instrument.exchange, instrument.currency)
        return Stock(instrument, "SMART", "EUR")

    @staticmethod
    def _ensure_utc(dt: datetime.datetime) -> datetime.datetime:
        """Normalize IB timestamps to timezone-aware UTC datetimes."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)

    def subscribe_to_data(self, instrument: Instrument | str, callback_function: Callable[..., Any]) -> None:
        """Subscribe to live tick-by-tick data for an instrument."""
        contract = self._build_stock_contract(instrument)
        try:
            self.ib.qualifyContracts(contract)
        except RuntimeError as exc:
            # In async startup paths, ib_insync sync helpers may raise this; proceed with raw contract.
            if "event loop is already running" not in str(exc):
                raise
        ticker_stream = self.ib.reqTickByTickData(contract, "AllLast")
        ticker_stream.updateEvent += callback_function

    def fetch_past_data(self, instrument: Instrument | str, days_back: int = 5) -> Sequence[Any]:
        """Fetch historical ticks for an instrument going back `days_back` days."""
        contract = self._build_stock_contract(instrument)
        self.ib.qualifyContracts(contract)

        target_start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
        end_time = datetime.datetime.now(datetime.timezone.utc)
        all_ticks: list[Any] = []
        max_iters = 200

        for _ in range(max_iters):
            if end_time <= target_start_time:
                break
            tick_chunk = self.ib.reqHistoricalTicks(
                contract,
                startDateTime="",
                endDateTime=end_time,
                numberOfTicks=1000,
                whatToShow="TRADES",
                useRth=False,
                ignoreSize=False,
            )
            if len(tick_chunk) == 0:
                break

            all_ticks = list(tick_chunk) + all_ticks
            oldest_time = min(self._ensure_utc(tick.time) for tick in tick_chunk)
            next_end_time = oldest_time - datetime.timedelta(microseconds=1)
            if next_end_time >= end_time:
                break
            end_time = next_end_time

            # Historical backfill is a cold path; a small pause avoids hammering IB.
            time.sleep(0.2)

        return all_ticks

    def fetch_ohlcv(
        self,
        instrument: Instrument | str,
        *,
        duration: str = "6 M",
        bar_size: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = False,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV bars from Interactive Brokers."""
        from ib_insync import util

        contract = self._build_stock_contract(instrument)
        self.ib.qualifyContracts(contract)

        bars = self.ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRth=use_rth,
            formatDate=1,
            keepUpToDate=False,
        )
        df = util.df(bars)
        if df is None or len(df) == 0:
            return pd.DataFrame()

        df = df.rename(columns={c: str(c).lower() for c in df.columns})
        cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[cols].copy()
        if "close" in df.columns:
            df = df.dropna(subset=["close"])
        return df


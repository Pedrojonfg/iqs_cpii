from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

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
        """Return symbols with a positive open position.

        Returns:
            A list of ticker symbols (e.g. `["AIR.PA", "RHM.DE"]`) currently held
            with position size > 0.
        """
        positions = self.ib.positions()
        return [pos.contract.symbol for pos in positions if pos.position > 0]

    def get_disp_money(self) -> float:
        """Get available buying power in EUR.

        Returns:
            Available funds as a float in EUR. Returns `0.0` if the tag is not
            found.
        """
        acc_values = self.ib.accountValues()
        for value in acc_values:
            if value.tag == "AvailableFunds" and value.currency == "EUR":
                return float(value.value)
        return 0.0

    def subscribe_to_data(self, symbol: str, callback_function: Callable[..., Any]) -> None:
        """Subscribe to live tick-by-tick data for `symbol`.

        The callback is attached to the `updateEvent` stream provided by
        `ib_insync`.

        Args:
            symbol: Ticker symbol to subscribe to.
            callback_function: Function called on updates (signature depends on
                `ib_insync` event payloads).
        """
        from ib_insync import Stock

        contract = Stock(symbol, "SMART", "EUR")
        self.ib.qualifyContracts(contract)
        
        ticker_stream = self.ib.reqTickByTickData(contract, 'AllLast')
        ticker_stream.updateEvent += callback_function

    def fetch_past_data(self, symbol: str, days_back: int = 5) -> Sequence[Any]:
        """Fetch historical ticks for `symbol` going back `days_back` days.

        Args:
            symbol: Ticker symbol.
            days_back: How many days of data to retrieve.

        Returns:
            A sequence of tick objects returned by `ib_insync`.
        """
        from ib_insync import Stock

        contract = Stock(symbol, "SMART", "EUR")
        self.ib.qualifyContracts(contract)
        
        target_start_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
        end_time = datetime.datetime.now(datetime.timezone.utc)
        
        all_ticks: list[Any] = []
        
        while end_time > target_start_time:
            tick_chunk = self.ib.reqHistoricalTicks(
                contract,
                startDateTime="",
                endDateTime=end_time,
                numberOfTicks=1000, 
                whatToShow="TRADES",
                useRth=False,
                ignoreSize=False
            ) 
            if len(tick_chunk)==0:
                break
            all_ticks = list(tick_chunk) + all_ticks
            end_time = tick_chunk[0].time
        
        return all_ticks
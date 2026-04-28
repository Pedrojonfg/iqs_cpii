from __future__ import annotations

from typing import Any

from ib_insync import IB, LimitOrder, Stock
from iqs.instruments import Instrument

class ExecutionHandler:
    """Order execution layer for Interactive Brokers via `ib_insync`."""

    def __init__(self, ib_connection: IB) -> None:
        """Create a new execution handler.

        Args:
            ib_connection: Connected `ib_insync.IB` instance.
        """
        self.ib: IB = ib_connection

    def disconnect(self) -> None:
        """Disconnect the underlying IB session."""
        self.ib.disconnect()
    
    def send_order(
        self,
        instrument: Instrument | str,
        action: str,
        quantity: float,
        entry_price: float,
        disp_money: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> None:
        """Send a limit order (or bracket order if TP/SL provided).

        Args:
            instrument: Instrument to trade. A bare symbol string is accepted as a
                backward-compatible fallback and will use `SMART` / `EUR`.
            action: `"BUY"` or `"SELL"` (case-insensitive).
            quantity: Order quantity (shares).
            entry_price: Limit price.
            disp_money: Available funds (used to validate BUY sizing).
            take_profit: Optional take-profit price. If non-zero (and/or
                `stop_loss` non-zero) a bracket order is used.
            stop_loss: Optional stop-loss price.

        Raises:
            ValueError: If inputs are invalid or insufficient buying power.
        """
        if isinstance(instrument, Instrument):
            contract_symbol = instrument.symbol
            contract_exchange = instrument.exchange
            contract_currency = instrument.currency
        else:
            contract_symbol = instrument
            contract_exchange = "SMART"
            contract_currency = "EUR"

        #Checks
        if len(contract_symbol) == 0:
            raise ValueError("Invalid ticker")
        
        action =action.upper()
        if action not in ["BUY", "SELL"]:
            raise ValueError("The action is not BUY or SELL")
        
        cost=quantity*entry_price
        if cost<=0 or quantity<0:
            raise ValueError("Incorrect Quantity-Price")
        if action=="BUY" and cost>disp_money:
            raise ValueError("Incorrect Quantity-Price")
        has_take_profit = take_profit != 0.0
        has_stop_loss = stop_loss != 0.0
        if has_take_profit != has_stop_loss:
            raise ValueError("take_profit and stop_loss must be both set or both zero")
        

        contract = Stock(contract_symbol, contract_exchange, contract_currency)
        self.ib.qualifyContracts(contract)

        if take_profit==0.0 and stop_loss==0.0:
            order= LimitOrder(action, quantity, entry_price)
            self.ib.placeOrder(contract, order)

        else:
            order_list=self.ib.bracketOrder(action, quantity, entry_price, take_profit, stop_loss)
            for order in order_list:
              self.ib.placeOrder(contract, order)  

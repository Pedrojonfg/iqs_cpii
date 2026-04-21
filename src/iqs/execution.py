from __future__ import annotations

from typing import Any

from ib_insync import IB, LimitOrder, Stock

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
        ticker: str,
        action: str,
        quantity: float,
        entry_price: float,
        disp_money: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> None:
        """Send a limit order (or bracket order if TP/SL provided).

        Args:
            ticker: Symbol to trade.
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
        #Checks
        if len(ticker)==0:
            raise ValueError("Invalid ticker")
        
        action =action.upper()
        if action not in ["BUY", "SELL"]:
            raise ValueError("The action is not BUY or SELL")
        
        cost=quantity*entry_price
        if cost<=0 or quantity<0:
            raise ValueError("Incorrect Quantity-Price")
        if action=="BUY" and cost>disp_money:
            raise ValueError("Incorrect Quantity-Price")
        

        contract= Stock(ticker, "SMART", "EUR")
        self.ib.qualifyContracts(contract)

        if take_profit==0.0 and stop_loss==0.0:
            order= LimitOrder(action, quantity, entry_price)
            self.ib.placeOrder(contract, order)

        else:
            order_list=self.ib.bracketOrder(action, quantity, entry_price, take_profit, stop_loss)
            for order in order_list:
              self.ib.placeOrder(contract, order)  

from __future__ import annotations

from typing import Any

from ib_insync import IB, LimitOrder, Stock

from iqs.data.instruments import Instrument


class ExecutionHandler:
    """Order execution layer for Interactive Brokers via `ib_insync`."""

    def __init__(self, ib_connection: IB) -> None:
        self.ib: IB = ib_connection

    def disconnect(self) -> None:
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
        if isinstance(instrument, Instrument):
            contract_symbol = instrument.symbol
            contract_exchange = instrument.exchange
            contract_currency = instrument.currency
        else:
            contract_symbol = instrument
            contract_exchange = "SMART"
            contract_currency = "EUR"

        if len(contract_symbol) == 0:
            raise ValueError("ticker must be a non-empty symbol")

        action = action.upper()
        if action not in ["BUY", "SELL"]:
            raise ValueError(f"action must be BUY or SELL, got: {action!r}")

        cost = quantity * entry_price
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got: {quantity}")
        if entry_price <= 0:
            raise ValueError(f"entry_price must be positive, got: {entry_price}")
        if cost <= 0:
            raise ValueError(f"order notional must be positive, got: {cost}")
        if action == "BUY" and cost > disp_money:
            raise ValueError(f"insufficient funds for BUY order: required={cost}, available={disp_money}")

        has_take_profit = take_profit != 0.0
        has_stop_loss = stop_loss != 0.0
        if has_take_profit != has_stop_loss:
            raise ValueError("take_profit and stop_loss must be both set or both zero")

        contract = Stock(contract_symbol, contract_exchange, contract_currency)
        self.ib.qualifyContracts(contract)

        if take_profit == 0.0 and stop_loss == 0.0:
            order = LimitOrder(action, quantity, entry_price)
            self.ib.placeOrder(contract, order)
        else:
            order_list: list[Any] = self.ib.bracketOrder(action, quantity, entry_price, take_profit, stop_loss)
            for order in order_list:
                self.ib.placeOrder(contract, order)


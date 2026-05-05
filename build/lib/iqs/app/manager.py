from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Protocol

from iqs.data.instruments import Instrument
from iqs.strategy.events import VolumeBar


class _BrokerLike(Protocol):
    def get_active_positions(self) -> list[str]: ...
    def get_position_market_value(self, symbol: str) -> float: ...
    def get_disp_money(self, currency: str = "EUR") -> float: ...


class _TechnicalLike(Protocol):
    def check_sell(self, ticker: Instrument | str) -> dict[str, Any]: ...
    def check_trade(self, ticker: Instrument | str) -> dict[str, Any]: ...


class _FundamentalLike(Protocol):
    def check_trade(self, ticker: str) -> str: ...


class _ExecutionLike(Protocol):
    def send_order(
        self,
        instrument: Instrument | str,
        action: str,
        quantity: float,
        entry_price: float,
        disp_money: float,
        take_profit: float = 0.0,
        stop_loss: float = 0.0,
    ) -> None: ...


class Manager:
    def __init__(
        self,
        broker: _BrokerLike,
        tickers: Iterable[Instrument],
        fundamental_analyzer: _FundamentalLike,
        technical_analyzer: _TechnicalLike,
        execution_handler: _ExecutionLike,
    ) -> None:
        self.broker: _BrokerLike = broker
        self.tickers: list[Instrument] = list(tickers)
        self.instrument_by_symbol: dict[str, Instrument] = {instrument.symbol: instrument for instrument in self.tickers}
        self.fundamental: _FundamentalLike = fundamental_analyzer
        self.technical: _TechnicalLike = technical_analyzer
        self.execution: _ExecutionLike = execution_handler

    async def on_volume_bar(self, bar: VolumeBar) -> None:
        logger = logging.getLogger("iqs")

        on_bar = getattr(self.technical, "on_volume_bar", None)
        if not callable(on_bar):
            logger.warning("on_volume_bar called but technical analyzer has no on_volume_bar(); ignoring")
            return

        decision = on_bar(bar)
        signal = decision.get("signal", "DON'T BUY")
        instrument = self.instrument_by_symbol.get(bar.symbol, Instrument(symbol=bar.symbol, exchange="SMART", currency="EUR"))

        if signal == "SELL":
            try:
                self.execution.send_order(
                    instrument,
                    action="SELL",
                    quantity=float(decision.get("quantity", 1.0)),
                    entry_price=float(decision["entry_price"]),
                    disp_money=self.broker.get_disp_money(instrument.currency),
                )
            except Exception:
                logger.exception("SELL execution failed for symbol=%s", bar.symbol)
            return

        if signal != "BUY":
            return

        ticker = instrument.symbol
        try:
            safe_check = getattr(self.fundamental, "check_trade_safe", None)
            if callable(safe_check):
                llmcheck = await safe_check(ticker)
            else:
                llmcheck = self.fundamental.check_trade(ticker)
        except Exception:
            logger.exception("Fundamental veto failed for ticker=%s; defaulting to VETO", ticker)
            llmcheck = "VETO"

        if llmcheck != "CLEAR":
            return

        try:
            self.execution.send_order(
                instrument,
                action="BUY",
                quantity=float(decision["quantity"]),
                entry_price=float(decision["entry_price"]),
                disp_money=self.broker.get_disp_money(instrument.currency),
                take_profit=float(decision.get("take_profit", 0.0)),
                stop_loss=float(decision.get("stop_loss", 0.0)),
            )
        except Exception:
            logger.exception("BUY execution failed for symbol=%s", bar.symbol)


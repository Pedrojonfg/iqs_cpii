from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Protocol

from iqs.instruments import Instrument


class _BrokerLike(Protocol):
    def get_active_positions(self) -> list[str]: ...
    def get_position_market_value(self, symbol: str) -> float: ...
    def get_disp_money(self, currency: str = "EUR") -> float: ...


class _TechnicalLike(Protocol):
    def check_sell(self, ticker: Instrument | str) -> dict[str, Any]: ...
    def check_trade(self, ticker: Instrument | str) -> dict[str, Any]: ...


class _FundamentalLike(Protocol):
    def check_trade(self, ticker: str) -> str: ...


class _FundamentalSafeLike(_FundamentalLike, Protocol):
    async def check_trade_safe(self, ticker: str) -> str: ...


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
    """
    Orchestrates entries/exits using technical analysis + a fundamental veto.
    """
    def __init__(
        self,
        broker: _BrokerLike,
        tickers: Iterable[Instrument],
        fundamental_analyzer: _FundamentalLike,
        technical_analyzer: _TechnicalLike,
        execution_handler: _ExecutionLike,
    ) -> None:
        """Create the strategy coordinator.

        Args:
            broker: Data access layer (positions, funds).
            tickers: Universe of tickers to consider for entries.
            fundamental_analyzer: Veto checks for entries.
            technical_analyzer: Signal generation for entries/exits.
            execution_handler: Order execution abstraction.
        """
        self.broker: _BrokerLike = broker
        self.tickers: list[Instrument] = list(tickers)
        self.instrument_by_symbol: dict[str, Instrument] = {instrument.symbol: instrument for instrument in self.tickers}
        self.fundamental: _FundamentalLike = fundamental_analyzer
        self.technical: _TechnicalLike = technical_analyzer
        self.execution: _ExecutionLike = execution_handler

    async def manage_exits(self) -> None:
        """Evaluate open positions and send sell orders when signaled."""
        logger = logging.getLogger("iqs")
        open_positions = self.broker.get_active_positions()
        failures = 0
        for ticker in open_positions:
            try:
                instrument = self.instrument_by_symbol.get(ticker, Instrument(symbol=ticker, exchange="SMART", currency="EUR"))
                decision = self.technical.check_sell(instrument)
                if decision.get("signal", "DON'T SELL") == "SELL":
                    self.execution.send_order(
                        instrument,
                        action="SELL",
                        quantity=float(decision["quantity"]),
                        entry_price=float(decision["entry_price"]),
                        disp_money=self.broker.get_disp_money(instrument.currency),
                    )
            except Exception:
                # Keep exits resilient: a single ticker shouldn't break the whole stage.
                failures += 1
                logger.exception("manage_exits failed for ticker=%s; continuing", ticker)
                continue
        if failures:
            logger.warning("manage_exits completed with %d ticker failure(s)", failures)

    async def manage_entries(self) -> None:
        """Evaluate universe tickers and send buy orders when allowed."""
        logger = logging.getLogger("iqs")
        failures = 0
        for instrument in self.tickers:
            try:
                ticker = instrument.symbol
                decision = self.technical.check_trade(instrument)
                if decision.get("signal", "DON'T BUY") == "BUY":
                    target_quantity = float(decision["quantity"])
                    entry_price = float(decision["entry_price"])
                    target_value = target_quantity * entry_price
                    current_value = self.broker.get_position_market_value(ticker)
                    if current_value >= target_value:
                        logger.info(
                            "Skipping BUY for ticker=%s: current position value %.2f already covers target %.2f",
                            ticker,
                            current_value,
                            target_value,
                        )
                        continue
                    # Prefer resilient path when available (async + timeout/breaker).
                    safe_check = getattr(self.fundamental, "check_trade_safe", None)
                    if callable(safe_check):
                        llmcheck = await safe_check(ticker)
                    else:
                        llmcheck = self.fundamental.check_trade(ticker)
                    if llmcheck == "CLEAR":
                        self.execution.send_order(
                            instrument,
                            action="BUY",
                            quantity=target_quantity,
                            entry_price=entry_price,
                            disp_money=self.broker.get_disp_money(instrument.currency),
                            take_profit=float(decision.get("take_profit", 0.0)),
                            stop_loss=float(decision.get("stop_loss", 0.0)),
                        )
            except Exception:
                # Keep entries resilient: one ticker failure shouldn't kill the stage.
                failures += 1
                logger.exception("manage_entries failed for ticker=%s; continuing", ticker)
                continue
        if failures:
            logger.warning("manage_entries completed with %d ticker failure(s)", failures)


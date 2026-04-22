from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class _BrokerLike(Protocol):
    def get_active_positions(self) -> list[str]: ...
    def get_disp_money(self) -> float: ...


class _TechnicalLike(Protocol):
    def check_sell(self, ticker: str) -> dict[str, Any]: ...
    def check_trade(self, ticker: str) -> dict[str, Any]: ...


class _FundamentalLike(Protocol):
    def check_trade(self, ticker: str) -> str: ...


class _ExecutionLike(Protocol):
    def send_order(
        self,
        ticker: str,
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
        tickers: Iterable[str],
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
        self.tickers: list[str] = list(tickers)
        self.fundamental: _FundamentalLike = fundamental_analyzer
        self.technical: _TechnicalLike = technical_analyzer
        self.execution: _ExecutionLike = execution_handler

    async def manage_exits(self) -> None:
        """Evaluate open positions and send sell orders when signaled."""
        open_positions = self.broker.get_active_positions()
        for ticker in open_positions:
            try:
                decision = self.technical.check_sell(ticker)
                if decision.get("signal", "DON'T SELL") == "SELL":
                    self.execution.send_order(
                        ticker,
                        action="SELL",
                        quantity=float(decision["quantity"]),
                        entry_price=float(decision["entry_price"]),
                        disp_money=self.broker.get_disp_money(),
                    )
            except Exception:
                # Keep exits resilient: a single ticker shouldn't break the whole stage.
                continue

    async def manage_entries(self) -> None:
        """Evaluate universe tickers and send buy orders when allowed."""
        for ticker in self.tickers:
            try:
                decision = self.technical.check_trade(ticker)
                if decision.get("signal", "DON'T BUY") == "BUY":
                    # Prefer resilient path when available (async + timeout/breaker).
                    llmcheck = (
                        await self.fundamental.check_trade_safe(ticker)  # type: ignore[attr-defined]
                        if hasattr(self.fundamental, "check_trade_safe")
                        else self.fundamental.check_trade(ticker)
                    )
                    if llmcheck == "CLEAR":
                        self.execution.send_order(
                            ticker,
                            action="BUY",
                            quantity=float(decision["quantity"]),
                            entry_price=float(decision["entry_price"]),
                            disp_money=self.broker.get_disp_money(),
                            take_profit=float(decision.get("take_profit", 0.0)),
                            stop_loss=float(decision.get("stop_loss", 0.0)),
                        )
            except Exception:
                # Keep entries resilient: one ticker failure shouldn't kill the stage.
                continue


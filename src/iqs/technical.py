from __future__ import annotations

from typing import Any


class TechnicalAnalyzer:
    """Technical analysis signal generator (project-defined)."""

    def __init__(self) -> None:
        """Create a technical analyzer instance."""
        pass

    def check_trade(self, ticker: str) -> dict[str, Any]:
        """
        Return a dict with at least:
        - signal: "BUY" | "DON'T BUY"
        - quantity: float
        - entry_price: float
        - take_profit: float (optional)
        - stop_loss: float (optional)
        """
        raise NotImplementedError("Implement technical logic (check_trade).")

    def check_sell(self, ticker: str) -> dict[str, Any]:
        """
        Return a dict with at least:
        - signal: "SELL" | "DON'T SELL"
        - quantity: float
        - entry_price: float
        """
        raise NotImplementedError("Implement technical logic (check_sell).")


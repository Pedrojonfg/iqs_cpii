from __future__ import annotations

from iqs.news import NewsFetcher
from iqs.nlp_veto import LLMCheck

class FundamentalAnalyzer:
    """Fundamental / event-driven veto checks for entry decisions."""

    def __init__(self) -> None:
        """Create the analyzer with a news fetcher and LLM veto module."""
        self.news: NewsFetcher = NewsFetcher()
        self.analysis: LLMCheck = LLMCheck()
    
    def check_trade(self, ticker: str) -> str:
        """Return `"CLEAR"` if the entry is allowed, otherwise `"VETO"`.

        Args:
            ticker: Ticker symbol.

        Returns:
            Decision string produced by the veto layer.
        """
        safe_news: str = self.news.newsfetcher(ticker)
        decision: str = self.analysis.decide(ticker, safe_news)
        return decision
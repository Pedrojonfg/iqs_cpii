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

    async def check_trade_safe(self, ticker: str) -> str:
        """
        Resilient version:
        - news fetching is protected by timeout + circuit breaker
        - LLM veto is protected by timeout + circuit breaker
        - fallback is conservative: VETO on any failure
        """

        safe_news = await self.news.newsfetcher_safe(ticker)
        decision = await self.analysis.decide_safe_async(ticker, safe_news)
        return decision
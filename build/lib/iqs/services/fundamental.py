from __future__ import annotations

from iqs.services.news import NewsFetcher
from iqs.services.nlp_veto import LLMCheck


class FundamentalAnalyzer:
    """Fundamental / event-driven veto checks for entry decisions."""

    def __init__(self) -> None:
        self.news: NewsFetcher = NewsFetcher()
        self.analysis: LLMCheck = LLMCheck()

    def check_trade(self, ticker: str) -> str:
        safe_news: str = self.news.newsfetcher(ticker)
        decision: str = self.analysis.decide(ticker, safe_news)
        return decision

    async def check_trade_safe(self, ticker: str) -> str:
        safe_news = await self.news.newsfetcher_safe(ticker)
        decision = await self.analysis.decide_safe_async(ticker, safe_news)
        return decision


from __future__ import annotations

from typing import Any

import yfinance as yf

from iqs.ops.resilience import CircuitBreaker, run_sync_with_timeout


class NewsFetcher:
    """Fetch and sanitize recent news headlines for a ticker."""

    def __init__(self) -> None:
        self.max_chars_headline: int = 100
        self.max_total_headlines: int = 15
        self.timeout_s: float = 5.0
        self.breaker: CircuitBreaker = CircuitBreaker(fail_threshold=3, reset_after_s=120.0)

    def fetch_headlines(self, ticker: str) -> list[str]:
        raw_news = yf.Ticker(ticker).news or []
        clean_headlines: list[str] = []
        for article in raw_news[: self.max_total_headlines]:
            content: dict[str, Any] = article.get("content", {}) or {}
            headline: str = str(content.get("title", "") or "")
            if headline:
                clean_headlines.append(headline)
        return clean_headlines

    async def fetch_headlines_safe(self, ticker: str) -> list[str]:
        if not self.breaker.allow():
            return []
        try:
            headlines = await run_sync_with_timeout(lambda: self.fetch_headlines(ticker), timeout_s=self.timeout_s)
            self.breaker.record_success()
            return headlines
        except Exception:
            self.breaker.record_failure()
            return []

    @staticmethod
    def _escape_xml_text(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    def format_and_sanitize(self, clean_headlines: list[str]) -> str:
        healthy_headlines: list[str] = []
        for headline in clean_headlines:
            headline = headline[: self.max_chars_headline]
            headline = self._escape_xml_text(headline)
            headline = "<new>" + headline + "</new>"
            healthy_headlines.append(headline)
        return "<news>" + ("\n".join(healthy_headlines)) + "</news>"

    def newsfetcher(self, ticker: str) -> str:
        return self.format_and_sanitize(self.fetch_headlines(ticker))

    async def newsfetcher_safe(self, ticker: str) -> str:
        headlines = await self.fetch_headlines_safe(ticker)
        return self.format_and_sanitize(headlines)


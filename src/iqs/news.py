from __future__ import annotations

from typing import Any

import yfinance as yf

from iqs.resilience import CircuitBreaker, run_sync_with_timeout


class NewsFetcher:
    """Fetch and sanitize recent news headlines for a ticker."""

    def __init__(self) -> None:
        """Create a news fetcher with conservative limits."""
        self.max_chars_headline: int = 100
        self.max_total_headlines: int = 15
        self.timeout_s: float = 5.0
        self.breaker: CircuitBreaker = CircuitBreaker(fail_threshold=3, reset_after_s=120.0)
    
    def fetch_headlines(self, ticker: str) -> list[str]:
        """Fetch raw headlines from Yahoo Finance via `yfinance`.

        Args:
            ticker: Ticker symbol.

        Returns:
            A list of headline strings (may be empty).
        """
        raw_news = yf.Ticker(ticker).news or []
        clean_headlines: list[str] = []
        for article in raw_news[:self.max_total_headlines]:
            content: dict[str, Any] = article.get("content", {}) or {}
            headline: str = str(content.get("title", "") or "")
            if headline:
                clean_headlines.append(headline)
        return clean_headlines

    async def fetch_headlines_safe(self, ticker: str) -> list[str]:
        """
        Resilient wrapper: timeout + circuit breaker + safe fallback.
        """

        if not self.breaker.allow():
            return []
        try:
            headlines = await run_sync_with_timeout(lambda: self.fetch_headlines(ticker), timeout_s=self.timeout_s)
            self.breaker.record_success()
            return headlines
        except Exception:
            self.breaker.record_failure()
            return []
    
    def format_and_sanitize(self, clean_headlines: list[str]) -> str:
        """Sanitize and wrap headlines into a simple XML payload.

        The output is designed to be passed to an LLM while reducing prompt
        injection surface (angle brackets are stripped and each entry is wrapped
        in `<new>` tags).

        Args:
            clean_headlines: List of raw headline strings.

        Returns:
            A single string wrapped in `<news>...</news>`.
        """
        healthy_headlines: list[str] = []
        for headline in clean_headlines:
            headline = headline[:self.max_chars_headline]
            headline= headline.replace("<", " ").replace(">", " ")
            headline = "<new>"+ headline +"</new>"
            healthy_headlines.append(headline)
        headline_string= "<news>"+ ("\n".join(healthy_headlines))+ "</news>"
        return headline_string
    
    def newsfetcher(self, ticker: str) -> str:
        """Fetch headlines and return sanitized XML payload."""
        return self.format_and_sanitize(self.fetch_headlines(ticker))

    async def newsfetcher_safe(self, ticker: str) -> str:
        """
        Resilient version of `newsfetcher`:
        - returns an empty `<news></news>` payload if fetching fails.
        """

        headlines = await self.fetch_headlines_safe(ticker)
        return self.format_and_sanitize(headlines)
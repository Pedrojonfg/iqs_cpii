from __future__ import annotations

from typing import Any

import yfinance as yf

class NewsFetcher:
    """Fetch and sanitize recent news headlines for a ticker."""

    def __init__(self) -> None:
        """Create a news fetcher with conservative limits."""
        self.max_chars_headline: int = 100
        self.max_total_headlines: int = 15
    
    def fetch_headlines(self, ticker: str) -> list[str]:
        """Fetch raw headlines from Yahoo Finance via `yfinance`.

        Args:
            ticker: Ticker symbol.

        Returns:
            A list of headline strings (may be empty).
        """
        raw_news: list[dict[str, Any]] = yf.Ticker(ticker).news
        clean_headlines: list[str] = []
        for article in raw_news[:self.max_total_headlines]:
            content: dict[str, Any] = article.get("content", {}) or {}
            headline: str = str(content.get("title", "") or "")
            if headline:
                clean_headlines.append(headline)
        return clean_headlines
    
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
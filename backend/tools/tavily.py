"""Tavily web search client wrapper (Tier 2 signal source).

Wraps the tavily-python SDK for async-friendly use.
Retry: 2 retries with exponential backoff on transient errors.
"""
from __future__ import annotations

import asyncio
from typing import Any

from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential


class TavilySearchClient:
    """Thin wrapper around TavilyClient for Tier 2 signal acquisition."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = TavilyClient(api_key=api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search(
        self,
        query: str,
        max_results: int = 10,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Run a web search and return result dicts.

        Each result dict has at least: url, title, content.
        """
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._client.search(
                query=query,
                max_results=max_results,
                days=days,
            ),
        )
        return results.get("results", [])

"""JSearch API client wrapper (job postings — Tier 1 signal source).

Uses RapidAPI JSearch endpoint. API key from config.api_keys.jsearch.
Retry: 2 retries with exponential backoff on transient errors.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class JSearchClient:
    """Thin async wrapper around the JSearch RapidAPI endpoint."""

    BASE_URL = "https://jsearch.p.rapidapi.com"
    HOST = "jsearch.p.rapidapi.com"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": self.HOST,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search_jobs(
        self,
        company_name: str,
        days_ago: int = 30,
        num_pages: int = 1,
    ) -> list[dict[str, Any]]:
        """Search job postings for a company.

        Returns list of job dicts with at least:
          - job_id, job_title, job_description, date_posted
        """
        query = f"{company_name} IT infrastructure cloud"
        # JSearch date_posted valid values: all, today, 3days, week, month
        if days_ago <= 1:
            date_posted = "today"
        elif days_ago <= 3:
            date_posted = "3days"
        elif days_ago <= 7:
            date_posted = "week"
        else:
            date_posted = "month"
        params = {
            "query": query,
            "page": "1",
            "num_pages": str(num_pages),
            "date_posted": date_posted,
            "country": "us",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.BASE_URL}/search",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

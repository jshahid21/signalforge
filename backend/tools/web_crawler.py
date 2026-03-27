"""Lightweight URL crawler for product page extraction.

Used by capability map generator to extract product names and descriptions from a seller's
product/solutions page. Not used in the main signal pipeline.
"""
from __future__ import annotations

import re


_DEFAULT_TIMEOUT = 10.0
_MAX_CONTENT_LENGTH = 50_000  # chars


def _strip_html_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace. Not a full parser — best-effort."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


async def crawl_url(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch a URL and return its plain-text content (HTML stripped).

    Returns empty string on any fetch or parse failure (graceful degradation).
    """
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "SignalForge/1.0 (capability-map-generator)"},
            )
            response.raise_for_status()
            html = response.text
    except Exception:
        return ""

    text = _strip_html_tags(html)
    return text[:_MAX_CONTENT_LENGTH]

"""Lightweight URL crawler for product page extraction.

Used by capability map generator to extract product names and descriptions from a seller's
product/solutions page. Also used by seller intelligence extraction for website scraping.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse


_DEFAULT_TIMEOUT = 10.0
_MAX_CONTENT_LENGTH = 50_000  # chars

# Patterns for discovering high-value subpages from a seller's website
_SUBPAGE_PATTERNS = (
    "/product", "/solutions", "/platform", "/customers", "/case-stud",
    "/about", "/why-", "/features", "/services", "/pricing",
)
_MAX_DISCOVERED_LINKS = 9


def _strip_html_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace. Not a full parser — best-effort."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


async def fetch_html(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch a URL and return raw HTML. Returns empty string on failure."""
    try:
        import httpx

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "SignalForge/1.0 (seller-intelligence)"},
            )
            response.raise_for_status()
            return response.text
    except Exception:
        return ""


def extract_links(html: str, base_url: str) -> list[str]:
    """Extract same-domain links from raw HTML matching high-value subpage patterns.

    Returns deduplicated list of absolute URLs (max _MAX_DISCOVERED_LINKS).
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    # Find all href attributes in <a> tags
    hrefs = re.findall(r'<a\s[^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)

    seen: set[str] = set()
    results: list[str] = []

    for href in hrefs:
        # Resolve relative URLs
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        # Same domain only
        if parsed.netloc.lower() != base_domain:
            continue

        # Normalize: strip fragment and trailing slash for dedup
        normalized = parsed._replace(fragment="").geturl().rstrip("/")

        # Skip the base URL itself
        base_normalized = parsed_base._replace(fragment="").geturl().rstrip("/")
        if normalized == base_normalized:
            continue

        # Check if path matches any high-value pattern
        path_lower = parsed.path.lower()
        if not any(pattern in path_lower for pattern in _SUBPAGE_PATTERNS):
            continue

        if normalized not in seen:
            seen.add(normalized)
            results.append(absolute)
            if len(results) >= _MAX_DISCOVERED_LINKS:
                break

    return results


async def crawl_url(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch a URL and return its plain-text content (HTML stripped).

    Returns empty string on any fetch or parse failure (graceful degradation).
    """
    html = await fetch_html(url, timeout)
    if not html:
        return ""

    text = _strip_html_tags(html)
    return text[:_MAX_CONTENT_LENGTH]

"""Tests for backend/tools/web_crawler.py — fetch_html, extract_links, crawl_url."""
from __future__ import annotations

import pytest

from backend.tools.web_crawler import (
    _strip_html_tags,
    extract_links,
    fetch_html,
    crawl_url,
)


# ---------------------------------------------------------------------------
# extract_links tests
# ---------------------------------------------------------------------------


class TestExtractLinks:
    def test_extracts_same_domain_links(self) -> None:
        html = """
        <html><body>
        <a href="/products/ml-ops">ML Ops</a>
        <a href="/about">About Us</a>
        <a href="/solutions/finops">FinOps</a>
        <a href="https://other.com/page">External</a>
        </body></html>
        """
        links = extract_links(html, "https://example.com")
        assert len(links) == 3
        assert any("/products/ml-ops" in link for link in links)
        assert any("/about" in link for link in links)
        assert any("/solutions/finops" in link for link in links)
        # External link excluded
        assert not any("other.com" in link for link in links)

    def test_filters_to_high_value_patterns(self) -> None:
        html = """
        <html><body>
        <a href="/blog/latest-news">Blog</a>
        <a href="/careers">Careers</a>
        <a href="/customers/case-studies">Case Studies</a>
        <a href="/products/analytics">Products</a>
        </body></html>
        """
        links = extract_links(html, "https://example.com")
        # Only /customers and /products match the patterns
        assert len(links) == 2
        assert any("/customers" in link for link in links)
        assert any("/products" in link for link in links)

    def test_deduplicates_links(self) -> None:
        html = """
        <html><body>
        <a href="/products/a">A</a>
        <a href="/products/a">A Again</a>
        <a href="/products/a#section">A with Fragment</a>
        </body></html>
        """
        links = extract_links(html, "https://example.com")
        assert len(links) == 1

    def test_resolves_relative_urls(self) -> None:
        html = '<a href="/solutions/cloud">Cloud</a>'
        links = extract_links(html, "https://example.com/page")
        assert len(links) == 1
        assert links[0].startswith("https://example.com")

    def test_excludes_base_url(self) -> None:
        html = """
        <a href="https://example.com/">Home</a>
        <a href="/">Home</a>
        <a href="/products/a">Products</a>
        """
        links = extract_links(html, "https://example.com/")
        # Should exclude self-links to homepage
        assert all("example.com/" in link and "/products" in link for link in links)

    def test_max_links_cap(self) -> None:
        # Generate 20 unique links matching patterns
        anchors = "\n".join(
            f'<a href="/products/item-{i}">Item {i}</a>' for i in range(20)
        )
        html = f"<html><body>{anchors}</body></html>"
        links = extract_links(html, "https://example.com")
        assert len(links) == 9  # _MAX_DISCOVERED_LINKS

    def test_empty_html_returns_empty(self) -> None:
        assert extract_links("", "https://example.com") == []

    def test_no_matching_links_returns_empty(self) -> None:
        html = '<a href="/blog/post">Blog</a><a href="/careers">Careers</a>'
        links = extract_links(html, "https://example.com")
        assert links == []

    def test_case_insensitive_pattern_matching(self) -> None:
        html = '<a href="/About">About</a><a href="/SOLUTIONS/x">X</a>'
        links = extract_links(html, "https://example.com")
        assert len(links) == 2


# ---------------------------------------------------------------------------
# _strip_html_tags tests
# ---------------------------------------------------------------------------


class TestStripHtmlTags:
    def test_strips_basic_tags(self) -> None:
        assert _strip_html_tags("<p>Hello</p>") == "Hello"

    def test_strips_scripts_and_styles(self) -> None:
        html = "<script>alert('x')</script><style>.foo{}</style><p>Content</p>"
        assert _strip_html_tags(html) == "Content"

    def test_collapses_whitespace(self) -> None:
        html = "<p>Hello</p>   <p>World</p>"
        assert _strip_html_tags(html) == "Hello World"


# ---------------------------------------------------------------------------
# fetch_html / crawl_url integration (mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetchHtml:
    @pytest.mark.asyncio
    async def test_returns_empty_on_network_error(self) -> None:
        result = await fetch_html("https://nonexistent.invalid.example.com", timeout=2)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_url(self) -> None:
        result = await fetch_html("not-a-url", timeout=2)
        assert result == ""


class TestCrawlUrl:
    @pytest.mark.asyncio
    async def test_returns_empty_on_network_error(self) -> None:
        result = await crawl_url("https://nonexistent.invalid.example.com", timeout=2)
        assert result == ""

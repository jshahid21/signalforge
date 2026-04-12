"""Tests for backend/agents/seller_intelligence.py — extraction agent logic."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.seller_intelligence import (
    _build_extraction_prompt,
    _parse_extraction_response,
    _validate_url,
    extract_seller_intelligence,
    extract_and_save_seller_intelligence,
)
from backend.config.loader import SellerIntelligence


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_accepts_https(self) -> None:
        assert _validate_url("https://example.com") == "https://example.com"

    def test_rejects_http(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_url("http://example.com")

    def test_rejects_no_scheme(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_url("example.com")

    def test_strips_whitespace(self) -> None:
        assert _validate_url("  https://example.com  ") == "https://example.com"

    def test_rejects_empty_domain(self) -> None:
        with pytest.raises(ValueError, match="no domain"):
            _validate_url("https://")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


class TestBuildExtractionPrompt:
    def test_includes_website_content(self) -> None:
        prompt = _build_extraction_prompt("This is a B2B company selling ML tools.")
        assert "ML tools" in prompt
        assert "differentiators" in prompt
        assert "sales_plays" in prompt
        assert "proof_points" in prompt
        assert "competitive_positioning" in prompt

    def test_truncates_long_content(self) -> None:
        long_text = "x" * 50_000
        prompt = _build_extraction_prompt(long_text)
        # The prompt should not include the full 50k chars
        assert len(prompt) < 50_000


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


VALID_LLM_RESPONSE = json.dumps({
    "differentiators": [
        "Best-in-class ML ops platform",
        "Zero-downtime deployment for models",
    ],
    "sales_plays": [
        {"play": "FinOps cost optimization", "category": "cost_optimization"},
        {"play": "ML model deployment acceleration", "category": "ml_ops"},
    ],
    "proof_points": [
        {"customer": "Acme Corp", "summary": "Reduced cloud costs by 40%"},
    ],
    "competitive_positioning": [
        "Unlike competitors, we offer real-time model monitoring",
    ],
})


class TestParseExtractionResponse:
    def test_parses_valid_json(self) -> None:
        result = _parse_extraction_response(VALID_LLM_RESPONSE)
        assert result is not None
        assert len(result.differentiators) == 2
        assert len(result.sales_plays) == 2
        assert result.sales_plays[0].category == "cost_optimization"
        assert len(result.proof_points) == 1
        assert result.proof_points[0].customer == "Acme Corp"
        assert len(result.competitive_positioning) == 1
        assert result.last_scraped is not None

    def test_parses_json_with_surrounding_text(self) -> None:
        response = f"Here is the extracted intelligence:\n{VALID_LLM_RESPONSE}\n\nDone."
        result = _parse_extraction_response(response)
        assert result is not None
        assert len(result.differentiators) == 2

    def test_returns_none_on_invalid_json(self) -> None:
        assert _parse_extraction_response("not json at all") is None

    def test_returns_none_on_empty(self) -> None:
        assert _parse_extraction_response("") is None

    def test_handles_empty_categories(self) -> None:
        response = json.dumps({
            "differentiators": [],
            "sales_plays": [],
            "proof_points": [],
            "competitive_positioning": [],
        })
        result = _parse_extraction_response(response)
        assert result is not None
        assert result.differentiators == []
        assert result.sales_plays == []

    def test_handles_partial_sales_plays(self) -> None:
        response = json.dumps({
            "differentiators": ["Good product"],
            "sales_plays": [
                {"play": "Valid", "category": "valid"},
                {"play": "Missing category"},  # Missing category field
                "not a dict",
            ],
            "proof_points": [],
            "competitive_positioning": [],
        })
        result = _parse_extraction_response(response)
        assert result is not None
        assert len(result.sales_plays) == 1  # Only the valid one

    def test_handles_partial_proof_points(self) -> None:
        response = json.dumps({
            "differentiators": [],
            "sales_plays": [],
            "proof_points": [
                {"customer": "Valid", "summary": "Good"},
                {"customer": "Missing summary"},  # Missing summary
            ],
            "competitive_positioning": [],
        })
        result = _parse_extraction_response(response)
        assert result is not None
        assert len(result.proof_points) == 1


# ---------------------------------------------------------------------------
# Full extraction pipeline (mocked HTTP + LLM)
# ---------------------------------------------------------------------------


SAMPLE_HTML = """
<html><head><title>TestCo - ML Platform</title></head>
<body>
<nav>
    <a href="/products/ml-ops">ML Ops</a>
    <a href="/customers">Customers</a>
    <a href="/about">About</a>
</nav>
<h1>TestCo - The ML Platform</h1>
<p>Best-in-class ML operations for enterprise teams.</p>
<p>Trusted by Fortune 500 companies.</p>
</body></html>
"""


class TestExtractSellerIntelligence:
    @pytest.mark.asyncio
    async def test_full_pipeline_mocked(self) -> None:
        """Test the full extraction pipeline with mocked HTTP and LLM."""
        mock_response = MagicMock()
        mock_response.content = VALID_LLM_RESPONSE

        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.crawl_url", new_callable=AsyncMock) as mock_crawl,
            patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_llm_cls,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_crawl.return_value = "Subpage content about ML operations."

            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_cls.return_value = mock_llm

            result = await extract_seller_intelligence(
                "https://testco.com", "anthropic", "claude-sonnet-4-6"
            )

            assert isinstance(result, SellerIntelligence)
            assert len(result.differentiators) == 2
            assert result.sales_plays[0].category == "cost_optimization"
            assert result.last_scraped is not None

            # Verify fetch_html was called for homepage
            mock_fetch.assert_called_once_with("https://testco.com")
            # Verify subpages were crawled
            assert mock_crawl.call_count > 0

    @pytest.mark.asyncio
    async def test_raises_on_http_failure(self) -> None:
        with patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = ""  # Empty = fetch failed

            with pytest.raises(ValueError, match="Could not fetch"):
                await extract_seller_intelligence(
                    "https://unreachable.com", "anthropic", "claude-sonnet-4-6"
                )

    @pytest.mark.asyncio
    async def test_raises_on_invalid_url(self) -> None:
        with pytest.raises(ValueError, match="HTTPS"):
            await extract_seller_intelligence(
                "http://example.com", "anthropic", "claude-sonnet-4-6"
            )

    @pytest.mark.asyncio
    async def test_raises_on_llm_failure(self) -> None:
        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_llm_cls,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(side_effect=Exception("API rate limit"))
            mock_llm_cls.return_value = mock_llm

            with pytest.raises(RuntimeError, match="LLM extraction call failed"):
                await extract_seller_intelligence(
                    "https://testco.com", "anthropic", "claude-sonnet-4-6"
                )

    @pytest.mark.asyncio
    async def test_raises_on_unparseable_llm_response(self) -> None:
        mock_response = MagicMock()
        mock_response.content = "I cannot parse this website content."

        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_llm_cls,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_cls.return_value = mock_llm

            with pytest.raises(RuntimeError, match="unparseable"):
                await extract_seller_intelligence(
                    "https://testco.com", "anthropic", "claude-sonnet-4-6"
                )

    @pytest.mark.asyncio
    async def test_openai_provider_routing(self) -> None:
        mock_response = MagicMock()
        mock_response.content = VALID_LLM_RESPONSE

        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.crawl_url", new_callable=AsyncMock) as mock_crawl,
            patch("backend.agents.seller_intelligence.ChatOpenAI") as mock_openai_cls,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_crawl.return_value = ""

            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_openai_cls.return_value = mock_llm

            result = await extract_seller_intelligence(
                "https://testco.com", "openai", "gpt-4o-mini"
            )

            assert isinstance(result, SellerIntelligence)
            mock_openai_cls.assert_called_once()


# ---------------------------------------------------------------------------
# extract_and_save tests
# ---------------------------------------------------------------------------


class TestExtractAndSave:
    @pytest.mark.asyncio
    async def test_saves_to_config(self, tmp_config_dir) -> None:
        """Verify extraction result is saved to config."""
        from backend.config.loader import load_config, save_config

        # Set up config with LLM model
        config = load_config()
        config.api_keys.llm_model = "claude-sonnet-4-6"
        config.api_keys.llm_provider = "anthropic"
        save_config(config)

        mock_response = MagicMock()
        mock_response.content = VALID_LLM_RESPONSE

        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.crawl_url", new_callable=AsyncMock) as mock_crawl,
            patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_llm_cls,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_crawl.return_value = ""
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_cls.return_value = mock_llm

            result = await extract_and_save_seller_intelligence("https://testco.com")

            assert isinstance(result, SellerIntelligence)
            assert len(result.differentiators) == 2

            # Verify saved to config
            reloaded = load_config()
            assert reloaded.seller_profile.website_url == "https://testco.com"
            assert len(reloaded.seller_profile.seller_intelligence.differentiators) == 2

    @pytest.mark.asyncio
    async def test_raises_without_url(self, tmp_config_dir) -> None:
        with pytest.raises(ValueError, match="No website URL"):
            await extract_and_save_seller_intelligence()

    @pytest.mark.asyncio
    async def test_raises_without_llm_model(self, tmp_config_dir) -> None:
        from backend.config.loader import load_config, save_config

        config = load_config()
        config.seller_profile.website_url = "https://testco.com"
        save_config(config)

        with pytest.raises(ValueError, match="LLM model"):
            await extract_and_save_seller_intelligence()

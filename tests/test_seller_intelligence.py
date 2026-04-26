"""Tests for backend/agents/seller_intelligence.py — extraction agent logic."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.seller_intelligence import (
    _build_auto_link_prompt,
    _build_extraction_prompt,
    _parse_auto_link_response,
    _parse_extraction_response,
    _validate_url,
    auto_link_intelligence,
    extract_seller_intelligence,
    extract_seller_intelligence_from_text,
    extract_and_save_seller_intelligence,
)
from backend.config.capability_map import CapabilityMap, CapabilityMapEntry
from backend.config.loader import ProofPoint, SalesPlay, SellerIntelligence


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
        # Feed input above the current 120K extraction ceiling so truncation must engage.
        long_text = "x" * 200_000
        prompt = _build_extraction_prompt(long_text)
        assert len(prompt) < 200_000


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

    @pytest.mark.asyncio
    async def test_auto_links_after_scrape_when_cap_map_exists(
        self, tmp_config_dir, tmp_capability_map_path
    ) -> None:
        """Verify auto_link_intelligence is called after a successful scrape when a capability map exists."""
        from backend.config.capability_map import CapabilityMap, CapabilityMapEntry, save_capability_map
        from backend.config.loader import load_config, save_config

        # Set up config with LLM model
        config = load_config()
        config.api_keys.llm_model = "claude-sonnet-4-6"
        config.api_keys.llm_provider = "anthropic"
        save_config(config)

        # Create a capability map
        cap_map = CapabilityMap(
            entries=[CapabilityMapEntry({"id": "test", "label": "Test", "solution_areas": ["Test Area"]})],
            version="1.0",
        )
        save_capability_map(cap_map)

        mock_response = MagicMock()
        mock_response.content = VALID_LLM_RESPONSE

        with (
            patch("backend.agents.seller_intelligence.fetch_html", new_callable=AsyncMock) as mock_fetch,
            patch("backend.agents.seller_intelligence.crawl_url", new_callable=AsyncMock) as mock_crawl,
            patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_llm_cls,
            patch("backend.agents.seller_intelligence.auto_link_intelligence", new_callable=AsyncMock) as mock_auto_link,
        ):
            mock_fetch.return_value = SAMPLE_HTML
            mock_crawl.return_value = ""
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_llm_cls.return_value = mock_llm
            mock_auto_link.return_value = {}

            await extract_and_save_seller_intelligence("https://testco.com")

            mock_auto_link.assert_called_once()


# ---------------------------------------------------------------------------
# Auto-link prompt and parsing tests
# ---------------------------------------------------------------------------


def _make_cap_map() -> CapabilityMap:
    return CapabilityMap(
        entries=[
            CapabilityMapEntry({
                "id": "data_platform",
                "label": "Data Platform",
                "solution_areas": ["Columnar storage", "Stream processing"],
            }),
            CapabilityMapEntry({
                "id": "ml_infra",
                "label": "ML Infrastructure",
                "solution_areas": ["Model training", "Inference optimization"],
            }),
        ],
        version="1.0",
    )


def _make_intelligence() -> SellerIntelligence:
    return SellerIntelligence(
        differentiators=["Best-in-class ML ops", "Zero-downtime deployments"],
        sales_plays=[
            SalesPlay(play="FinOps cost optimization", category="cost_optimization"),
            SalesPlay(play="ML model deployment", category="ml_ops"),
        ],
        proof_points=[
            ProofPoint(customer="Acme Corp", summary="Reduced costs by 40%"),
            ProofPoint(customer="BigCo", summary="2x faster model inference"),
        ],
    )


VALID_AUTO_LINK_RESPONSE = json.dumps({
    "data_platform": {
        "differentiators": [],
        "sales_plays": [{"play": "FinOps cost optimization", "category": "cost_optimization"}],
        "proof_points": [{"customer": "Acme Corp", "summary": "Reduced costs by 40%"}],
    },
    "ml_infra": {
        "differentiators": ["Best-in-class ML ops"],
        "sales_plays": [{"play": "ML model deployment", "category": "ml_ops"}],
        "proof_points": [{"customer": "BigCo", "summary": "2x faster model inference"}],
    },
})


class TestBuildAutoLinkPrompt:
    def test_includes_capability_ids_and_labels(self) -> None:
        cap_map = _make_cap_map()
        intelligence = _make_intelligence()
        prompt = _build_auto_link_prompt(
            [e.as_dict() for e in cap_map.entries], intelligence
        )
        assert "data_platform" in prompt
        assert "Data Platform" in prompt
        assert "ml_infra" in prompt
        assert "ML Infrastructure" in prompt

    def test_includes_intelligence_items(self) -> None:
        cap_map = _make_cap_map()
        intelligence = _make_intelligence()
        prompt = _build_auto_link_prompt(
            [e.as_dict() for e in cap_map.entries], intelligence
        )
        assert "Best-in-class ML ops" in prompt
        assert "FinOps cost optimization" in prompt
        assert "Acme Corp" in prompt


class TestParseAutoLinkResponse:
    def test_parses_valid_response(self) -> None:
        result = _parse_auto_link_response(VALID_AUTO_LINK_RESPONSE)
        assert result is not None
        assert "data_platform" in result
        assert "ml_infra" in result
        assert len(result["ml_infra"]["differentiators"]) == 1

    def test_returns_none_on_invalid_json(self) -> None:
        assert _parse_auto_link_response("not json") is None

    def test_returns_none_on_empty(self) -> None:
        assert _parse_auto_link_response("") is None

    def test_handles_surrounding_text(self) -> None:
        response = f"Here is the mapping:\n{VALID_AUTO_LINK_RESPONSE}\nDone."
        result = _parse_auto_link_response(response)
        assert result is not None
        assert "data_platform" in result


class TestAutoLinkIntelligence:
    @pytest.mark.asyncio
    async def test_links_items_to_entries(self, tmp_capability_map_path, tmp_config_dir) -> None:
        cap_map = _make_cap_map()
        intelligence = _make_intelligence()

        mock_response = MagicMock()
        mock_response.content = VALID_AUTO_LINK_RESPONSE

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await auto_link_intelligence(
                cap_map, intelligence, "anthropic", "claude-sonnet-4-6"
            )

        assert "data_platform" in result
        assert "ml_infra" in result
        # Verify entries were updated in-place
        dp = next(e for e in cap_map.entries if e.id == "data_platform")
        assert len(dp.proof_points) == 1
        assert dp.proof_points[0]["customer"] == "Acme Corp"
        ml = next(e for e in cap_map.entries if e.id == "ml_infra")
        assert ml.differentiators == ["Best-in-class ML ops"]

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_entries(self) -> None:
        cap_map = CapabilityMap(entries=[], version="1.0")
        intelligence = _make_intelligence()
        result = await auto_link_intelligence(cap_map, intelligence, "anthropic", "model")
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_intelligence(self) -> None:
        cap_map = _make_cap_map()
        intelligence = SellerIntelligence()
        result = await auto_link_intelligence(cap_map, intelligence, "anthropic", "model")
        assert result == {}

    @pytest.mark.asyncio
    async def test_handles_unknown_capability_ids(self, tmp_capability_map_path, tmp_config_dir) -> None:
        cap_map = _make_cap_map()
        intelligence = _make_intelligence()

        response_with_unknown = json.dumps({
            "unknown_id": {
                "differentiators": ["Something"],
                "sales_plays": [],
                "proof_points": [],
            },
            "data_platform": {
                "differentiators": ["Valid diff"],
                "sales_plays": [],
                "proof_points": [],
            },
        })
        mock_response = MagicMock()
        mock_response.content = response_with_unknown

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await auto_link_intelligence(
                cap_map, intelligence, "anthropic", "claude-sonnet-4-6"
            )

        # unknown_id is in result (from LLM) but not applied to any entry
        dp = next(e for e in cap_map.entries if e.id == "data_platform")
        assert dp.differentiators == ["Valid diff"]

    @pytest.mark.asyncio
    async def test_handles_unparseable_response(self, tmp_capability_map_path, tmp_config_dir) -> None:
        cap_map = _make_cap_map()
        intelligence = _make_intelligence()

        mock_response = MagicMock()
        mock_response.content = "I can't do that."

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await auto_link_intelligence(
                cap_map, intelligence, "anthropic", "claude-sonnet-4-6"
            )

        assert result == {}
        # Entries unchanged
        dp = next(e for e in cap_map.entries if e.id == "data_platform")
        assert dp.differentiators == []


# ---------------------------------------------------------------------------
# extract_seller_intelligence_from_text
# ---------------------------------------------------------------------------


class TestExtractFromText:

    _VALID_JSON = json.dumps({
        "differentiators": ["Cloud-native architecture"],
        "sales_plays": [{"play": "Cost reduction", "category": "cost_optimization"}],
        "proof_points": [{"customer": "Acme Corp", "summary": "Saved 30%"}],
        "competitive_positioning": ["Faster than legacy tools"],
    })

    @pytest.mark.asyncio
    async def test_extracts_from_text(self) -> None:
        mock_response = MagicMock()
        mock_response.content = self._VALID_JSON

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await extract_seller_intelligence_from_text(
                "We are a cloud-native platform.", "anthropic", "claude-sonnet-4-6",
            )

        assert isinstance(result, SellerIntelligence)
        assert result.differentiators == ["Cloud-native architecture"]
        assert len(result.sales_plays) == 1
        assert result.last_scraped is not None

    @pytest.mark.asyncio
    async def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="No text content"):
            await extract_seller_intelligence_from_text("", "anthropic", "claude-sonnet-4-6")

    @pytest.mark.asyncio
    async def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="No text content"):
            await extract_seller_intelligence_from_text("  \n  ", "anthropic", "claude-sonnet-4-6")

    @pytest.mark.asyncio
    async def test_truncates_long_text(self) -> None:
        mock_response = MagicMock()
        mock_response.content = self._VALID_JSON

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            long_text = "x" * 50_000
            result = await extract_seller_intelligence_from_text(
                long_text, "anthropic", "claude-sonnet-4-6",
            )

        # Should succeed (truncation happens internally)
        assert isinstance(result, SellerIntelligence)

    @pytest.mark.asyncio
    async def test_uses_openai_provider(self) -> None:
        mock_response = MagicMock()
        mock_response.content = self._VALID_JSON

        with patch("backend.agents.seller_intelligence.ChatOpenAI") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await extract_seller_intelligence_from_text(
                "Enterprise ML platform.", "openai", "gpt-4o-mini",
            )

        assert isinstance(result, SellerIntelligence)
        mock_cls.assert_called_once()


class TestExtractAndSaveWithText:

    _VALID_JSON = json.dumps({
        "differentiators": ["Fast deployment"],
        "sales_plays": [],
        "proof_points": [],
        "competitive_positioning": [],
    })

    @pytest.mark.asyncio
    async def test_saves_from_text(self, tmp_config_dir, tmp_capability_map_path) -> None:
        from backend.config.loader import load_config, save_config

        config = load_config()
        config.api_keys.llm_model = "claude-sonnet-4-6"
        config.api_keys.llm_provider = "anthropic"
        save_config(config)

        mock_response = MagicMock()
        mock_response.content = self._VALID_JSON

        with patch("backend.agents.seller_intelligence.ChatAnthropic") as mock_cls:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_llm

            result = await extract_and_save_seller_intelligence(text="Pitch deck content")

        assert isinstance(result, SellerIntelligence)
        assert result.differentiators == ["Fast deployment"]

        # Verify saved to config
        reloaded = load_config()
        assert reloaded.seller_profile.seller_intelligence.differentiators == ["Fast deployment"]


# ---------------------------------------------------------------------------
# Prompt generalization
# ---------------------------------------------------------------------------


class TestPromptGeneralization:

    def test_no_website_specific_language(self) -> None:
        prompt = _build_extraction_prompt("Sample content.")
        # First line should use generic language
        first_line = prompt.split("\n")[0].lower()
        assert "sales collateral" in first_line
        # Body should not say "website content" or "on the website"
        assert "from this website content" not in prompt.lower()
        assert "on the website" not in prompt.lower()
        assert "on the site" not in prompt.lower()

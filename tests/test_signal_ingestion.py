"""Tests for Signal Ingestion Agent — tiered logic with mocked API clients."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.signal_ingestion import (
    _TIER_1_DENSITY_THRESHOLD,
    _should_escalate_to_tier_2,
    compute_signal_density,
    estimate_ambiguity_score,
    run_signal_ingestion,
)
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import CompanyState, CostMetadata, RawSignal


def _make_company_state(company_id: str = "stripe") -> CompanyState:
    return CompanyState(
        company_id=company_id,
        company_name=company_id.capitalize(),
        status=PipelineStatus.PENDING,
        current_stage="init",
        raw_signals=[],
        qualified_signal=None,
        signal_qualified=False,
        research_result=None,
        solution_mapping=None,
        generated_personas=[],
        selected_personas=[],
        recommended_outreach_sequence=[],
        synthesis_outputs={},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=0,
            tier_2_calls=0,
            tier_3_calls=0,
            llm_tokens_used=0,
            estimated_cost_usd=0.0,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


def _make_job_signal(content: str = "Senior SRE kubernetes") -> RawSignal:
    return RawSignal(
        source="jsearch",
        signal_type="job_posting",
        content=content,
        url=None,
        published_at=None,
        tier=SignalTier.TIER_1,
    )


def _make_mock_capability_map(keywords: list[str] | None = None):
    cap_map = MagicMock()
    cap_map.all_keywords.return_value = keywords or ["kubernetes", "ml platform", "data warehouse"]
    return cap_map


class TestComputeSignalDensity:
    def test_counts_matching_job_postings(self) -> None:
        signals = [
            _make_job_signal("Senior SRE kubernetes infra"),
            _make_job_signal("ML platform engineer tensorflow"),
            _make_job_signal("Office manager"),  # no keyword match
        ]
        keywords = ["kubernetes", "ml platform"]
        assert compute_signal_density(signals, keywords) == 2

    def test_ignores_non_job_signals(self) -> None:
        signals = [
            RawSignal(
                source="tavily",
                signal_type="engineering_blog",
                content="kubernetes migration",
                url=None,
                published_at=None,
                tier=SignalTier.TIER_2,
            )
        ]
        # engineering_blog should not count toward density
        assert compute_signal_density(signals, ["kubernetes"]) == 0

    def test_zero_density_on_empty_signals(self) -> None:
        assert compute_signal_density([], ["kubernetes"]) == 0

    def test_zero_density_on_empty_keywords(self) -> None:
        signals = [_make_job_signal("kubernetes")]
        assert compute_signal_density(signals, []) == 0

    def test_case_insensitive_matching(self) -> None:
        signals = [_make_job_signal("Senior KUBERNETES Engineer")]
        assert compute_signal_density(signals, ["kubernetes"]) == 1


class TestShouldEscalateToTier2:
    def test_escalates_when_density_below_threshold(self) -> None:
        signals = [_make_job_signal("kubernetes")]
        keywords = ["kubernetes"]
        # density = 1, which is < 3
        escalate, reason = _should_escalate_to_tier_2(signals, keywords, None)
        assert escalate is True
        assert "density" in reason

    def test_no_escalation_when_density_at_threshold(self) -> None:
        signals = [
            _make_job_signal("kubernetes engineer"),
            _make_job_signal("kubernetes architect"),
            _make_job_signal("kubernetes platform lead"),
        ]
        keywords = ["kubernetes"]
        escalate, _ = _should_escalate_to_tier_2(signals, keywords, None)
        assert escalate is False

    def test_escalates_on_high_ambiguity_score(self) -> None:
        # Provide enough signals (density >= 3) but high ambiguity
        signals = [
            _make_job_signal("kubernetes engineer"),
            _make_job_signal("kubernetes architect"),
            _make_job_signal("kubernetes platform lead"),
        ]
        keywords = ["kubernetes"]
        escalate, reason = _should_escalate_to_tier_2(signals, keywords, 0.75)
        assert escalate is True
        assert "ambiguity" in reason

    def test_no_escalation_on_low_ambiguity(self) -> None:
        signals = [
            _make_job_signal("kubernetes engineer"),
            _make_job_signal("kubernetes architect"),
            _make_job_signal("kubernetes platform lead"),
        ]
        keywords = ["kubernetes"]
        escalate, _ = _should_escalate_to_tier_2(signals, keywords, 0.3)
        assert escalate is False


class TestRunSignalIngestion:
    @pytest.fixture
    def mock_jsearch(self) -> AsyncMock:
        client = AsyncMock()
        client.search_jobs.return_value = [
            {
                "job_title": "Senior SRE",
                "job_description": "kubernetes cloud platform infra",
                "job_apply_link": "https://example.com/job/1",
                "job_posted_at_datetime_utc": "2026-03-20T00:00:00Z",
            },
            {
                "job_title": "ML Platform Engineer",
                "job_description": "ml platform tensorflow data warehouse",
                "job_apply_link": None,
                "job_posted_at_datetime_utc": None,
            },
            {
                "job_title": "Data Engineer",
                "job_description": "data warehouse etl pipeline",
                "job_apply_link": None,
                "job_posted_at_datetime_utc": None,
            },
        ]
        return client

    @pytest.fixture
    def mock_tavily(self) -> AsyncMock:
        client = AsyncMock()
        client.search.return_value = [
            {
                "url": "https://stripe.engineering/blog",
                "title": "Scaling our data platform",
                "content": "We migrated our kubernetes infra...",
            }
        ]
        return client

    @pytest.mark.asyncio
    async def test_tier_1_always_executes(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes", "ml platform", "data warehouse"])

        updated_cs, cost = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=mock_jsearch,
            tavily_client=mock_tavily,
        )

        mock_jsearch.search_jobs.assert_called_once()
        assert len(updated_cs["raw_signals"]) >= 3
        assert cost > 0

    @pytest.mark.asyncio
    async def test_tier_2_not_called_when_density_sufficient(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        # Returns 3 matching job postings → density = 3 → no Tier 2
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes", "ml platform", "data warehouse"])

        await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=mock_jsearch,
            tavily_client=mock_tavily,
        )

        # density = 3 (all 3 jobs match keywords), so Tier 2 should NOT be called
        mock_tavily.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_tier_2_called_when_density_insufficient(
        self, mock_tavily: AsyncMock
    ) -> None:
        # Only 1 matching job → density < 3 → Tier 2 triggered.
        # run_tier_2 issues 3 parallel Tavily queries and cost accounting must
        # charge 3x _TIER_2_COST_PER_CALL (regression guard for issue #8 bug 2).
        from backend.agents.signal_ingestion import (
            _TIER_1_COST_PER_CALL,
            _TIER_2_COST_PER_CALL,
            _TIER_2_QUERIES_PER_CALL,
        )

        jsearch_low = AsyncMock()
        jsearch_low.search_jobs.return_value = [
            {
                "job_title": "Office Manager",
                "job_description": "manages office supplies",
                "job_apply_link": None,
                "job_posted_at_datetime_utc": None,
            }
        ]
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes"])

        updated_cs, cost = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=jsearch_low,
            tavily_client=mock_tavily,
        )

        assert mock_tavily.search.call_count == _TIER_2_QUERIES_PER_CALL
        # Cost must account for all 3 parallel queries, not just 1.
        expected = (
            _TIER_1_COST_PER_CALL
            + _TIER_2_QUERIES_PER_CALL * _TIER_2_COST_PER_CALL
        )
        assert cost == pytest.approx(expected)
        assert updated_cs["cost_metadata"]["tier_2_calls"] == _TIER_2_QUERIES_PER_CALL

    @pytest.mark.asyncio
    async def test_budget_exceeded_marks_failed(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        # current cost already at max
        updated_cs, cost = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=1.0,  # already at max
            max_budget_usd=1.0,
            jsearch_client=mock_jsearch,
            tavily_client=mock_tavily,
        )

        assert updated_cs["status"] == PipelineStatus.FAILED
        assert cost == 0.0
        mock_jsearch.search_jobs.assert_not_called()

    @pytest.mark.asyncio
    async def test_jsearch_error_recorded_but_continues(
        self, mock_tavily: AsyncMock
    ) -> None:
        jsearch_fail = AsyncMock()
        jsearch_fail.search_jobs.side_effect = Exception("API unavailable")
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        updated_cs, _ = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=jsearch_fail,
            tavily_client=mock_tavily,
        )

        # Should record error but not fail fatally
        assert len(updated_cs["errors"]) > 0
        assert updated_cs["errors"][0]["error_type"] in ("Exception",)

    @pytest.mark.asyncio
    async def test_cost_logged_in_metadata(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes", "ml platform", "data warehouse"])

        updated_cs, cost = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=mock_jsearch,
            tavily_client=mock_tavily,
        )

        assert updated_cs["cost_metadata"]["estimated_cost_usd"] == cost
        assert updated_cs["cost_metadata"]["tier_1_calls"] == 1

    @pytest.mark.asyncio
    async def test_budget_exceeded_on_tier2_marks_failed(
        self, mock_tavily: AsyncMock
    ) -> None:
        """Tier 2 required but budget insufficient → mark FAILED (spec §5.2)."""
        # Only 1 job returned → density < 3 → Tier 2 needed
        jsearch_low = AsyncMock()
        jsearch_low.search_jobs.return_value = [
            {
                "job_title": "Office Manager",
                "job_description": "manages office",
                "job_apply_link": None,
                "job_posted_at_datetime_utc": None,
            }
        ]
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes"])

        # Budget: 0.001 (only covers Tier 1, not Tier 2 which costs 0.005)
        updated_cs, _ = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=0.002,  # enough for Tier 1 (0.001) but not Tier 2 (0.005)
            jsearch_client=jsearch_low,
            tavily_client=mock_tavily,
        )

        assert updated_cs["status"] == PipelineStatus.FAILED
        assert any(
            e["error_type"] == "budget_exceeded"
            for e in updated_cs["errors"]
        )
        mock_tavily.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_ambiguity_triggers_tier2_when_density_sufficient(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        """Tier 2 triggered by ambiguity > 0.7 even when density >= 3 (spec §7.1).

        Tier 2 fires 3 parallel Tavily queries (issue #8 bug 2 regression guard).
        """
        from backend.agents.signal_ingestion import _TIER_2_QUERIES_PER_CALL

        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes", "ml platform", "data warehouse"])

        # LLM reports high ambiguity (signal is stale/vague)
        with patch(
            "backend.agents.signal_qualification.call_llm_severity",
            new=AsyncMock(
                return_value=(
                    {"recency": 0.1, "specificity": 0.1, "technical_depth": 0.5, "buying_intent": 0.5},
                    10,
                )
            ),
        ):
            updated_cs, _ = await run_signal_ingestion(
                cs=cs,
                capability_map=cap_map,
                current_total_cost=0.0,
                max_budget_usd=1.0,
                jsearch_client=mock_jsearch,
                tavily_client=mock_tavily,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
            )

        # ambiguity = 1 - mean(0.1, 0.1) = 0.9 > 0.7 → Tier 2 triggered.
        # Tier 2 fires N parallel queries.
        assert mock_tavily.search.call_count == _TIER_2_QUERIES_PER_CALL
        # Assert the queries are distinct (meaningful parallelism, not duplicates).
        call_queries = [call.args[0] if call.args else call.kwargs.get("query") for call in mock_tavily.search.call_args_list]
        assert len(set(call_queries)) == _TIER_2_QUERIES_PER_CALL, f"Expected distinct queries, got {call_queries}"
        reasons = " ".join(updated_cs["cost_metadata"]["tier_escalation_reasons"])
        assert "ambiguity" in reasons

    @pytest.mark.asyncio
    async def test_tier3_eligible_logged_when_enterprise_signals(
        self, mock_jsearch: AsyncMock, mock_tavily: AsyncMock
    ) -> None:
        """Tier 3 eligibility is detected and logged when enterprise indicators present."""
        # Tavily returns enterprise-scale signal
        mock_tavily.search.return_value = [
            {
                "url": "https://example.com/blog",
                "title": "Platform Engineering at scale",
                "content": "We run platform engineering for thousands of engineers",
            },
            {
                "url": "https://example.com/blog2",
                "title": "Enterprise infrastructure",
                "content": "Our enterprise platform scales globally",
            },
        ]
        # Only 1 matching job → density < 3 → Tier 2 triggered
        jsearch_low = AsyncMock()
        jsearch_low.search_jobs.return_value = [
            {
                "job_title": "Office Manager",
                "job_description": "office management",
                "job_apply_link": None,
                "job_posted_at_datetime_utc": None,
            }
        ]
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map(["kubernetes"])

        updated_cs, _ = await run_signal_ingestion(
            cs=cs,
            capability_map=cap_map,
            current_total_cost=0.0,
            max_budget_usd=1.0,
            jsearch_client=jsearch_low,
            tavily_client=mock_tavily,
        )

        # Tier 3 eligibility should be logged in escalation reasons
        reasons = " ".join(updated_cs["cost_metadata"]["tier_escalation_reasons"])
        assert "tier_3" in reasons

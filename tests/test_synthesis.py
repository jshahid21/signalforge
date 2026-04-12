"""Tests for Synthesis Agent — all output fields populated, graceful degradation."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.synthesis import (
    _build_enrichment_context,
    _make_fallback_synthesis,
    _parse_synthesis_response,
    run_synthesis,
)
from backend.config.capability_map import CapabilityMap, CapabilityMapEntry
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    Persona,
    QualifiedSignal,
    ResearchResult,
    SolutionMappingOutput,
)


def _make_persona(persona_id: str = "p1", title: str = "Head of Platform Engineering") -> Persona:
    return Persona(
        persona_id=persona_id,
        title=title,
        targeting_reason="Owns platform infra.",
        role_type="technical_buyer",
        seniority_level="director",
        priority_score=0.9,
        is_custom=False,
        is_edited=False,
    )


def _make_company_state(
    with_personas: bool = True,
    selected_persona_ids: list[str] | None = None,
) -> CompanyState:
    persona = _make_persona("p1")
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="synthesis",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id="stripe",
            summary="Hiring platform engineers for kubernetes infrastructure.",
            signal_type="job_posting",
            keywords_matched=["kubernetes"],
            deterministic_score=0.6,
            llm_severity_score=0.75,
            composite_score=0.69,
            tier_used=SignalTier.TIER_1,
            raw_signals=[],
            qualified=True,
            disqualification_reason=None,
            partial=False,
            signal_ambiguity_score=0.25,
        ),
        signal_qualified=True,
        research_result=ResearchResult(
            company_context="Stripe is a payments company.",
            tech_stack=["kubernetes"],
            hiring_signals="Scaling platform engineering.",
            partial=False,
        ),
        industry=None,
        solution_mapping=SolutionMappingOutput(
            core_problem="Scaling Kubernetes infrastructure for global payments.",
            solution_areas=["Container orchestration", "Platform automation"],
            inferred_areas=[],
            matched_capability_ids=[],
            confidence_score=75,
            reasoning="Strong infra signal.",
        ),
        generated_personas=[persona] if with_personas else [],
        selected_personas=selected_persona_ids if selected_persona_ids is not None else ["p1"],
        recommended_outreach_sequence=["p1"],
        synthesis_outputs={},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=1, tier_2_calls=0, tier_3_calls=0,
            llm_tokens_used=0, estimated_cost_usd=0.005,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


_VALID_SYNTHESIS_JSON = """{
  "core_pain_point": "Stripe's Kubernetes clusters are hitting capacity limits.",
  "technical_context": "They use kubernetes and go for platform services.",
  "solution_alignment": "Container orchestration and automation directly address this.",
  "persona_targeting": "Head of Platform Engineering owns this problem directly.",
  "buyer_relevance": "Both operational risk and cost efficiency are at stake.",
  "value_hypothesis": "Reduce infrastructure incidents by 40% while cutting cloud spend.",
  "risk_if_ignored": "Continued manual ops leads to SLA breaches as scale increases."
}"""


class TestParseSynthesisResponse:
    def test_parses_valid_json(self) -> None:
        result = _parse_synthesis_response(_VALID_SYNTHESIS_JSON)
        assert result is not None
        assert "core_pain_point" in result
        assert "risk_if_ignored" in result

    def test_returns_none_on_invalid_json(self) -> None:
        assert _parse_synthesis_response("not json") is None

    def test_returns_none_on_missing_fields(self) -> None:
        assert _parse_synthesis_response('{"core_pain_point": "test"}') is None

    def test_extracts_json_from_prose(self) -> None:
        result = _parse_synthesis_response(f"Here is the synthesis:\n{_VALID_SYNTHESIS_JSON}")
        assert result is not None


class TestFallbackSynthesis:
    def test_all_fields_populated(self) -> None:
        result = _make_fallback_synthesis("Stripe", "scaling problem", "CTO")
        assert result["core_pain_point"]
        assert result["technical_context"]
        assert result["solution_alignment"]
        assert result["persona_targeting"]
        assert result["buyer_relevance"]
        assert result["value_hypothesis"]
        assert result["risk_if_ignored"]


class TestRunSynthesis:
    @pytest.mark.asyncio
    async def test_all_fields_populated_with_mock_llm(self) -> None:
        cs = _make_company_state()

        with patch("backend.agents.synthesis.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _VALID_SYNTHESIS_JSON
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, cost = await run_synthesis(
                cs=cs,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert "p1" in updated_cs["synthesis_outputs"]
        synthesis = updated_cs["synthesis_outputs"]["p1"]
        assert synthesis["core_pain_point"]
        assert synthesis["technical_context"]
        assert synthesis["solution_alignment"]
        assert synthesis["persona_targeting"]
        assert synthesis["buyer_relevance"]
        assert synthesis["value_hypothesis"]
        assert synthesis["risk_if_ignored"]
        assert cost > 0

    @pytest.mark.asyncio
    async def test_no_llm_uses_fallback(self) -> None:
        cs = _make_company_state()
        updated_cs, cost = await run_synthesis(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert "p1" in updated_cs["synthesis_outputs"]
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_marks_failed(self) -> None:
        cs = _make_company_state()
        updated_cs, cost = await run_synthesis(
            cs=cs,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=1.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["status"] == PipelineStatus.FAILED
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_updates_stage_to_draft(self) -> None:
        cs = _make_company_state()
        updated_cs, _ = await run_synthesis(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["current_stage"] == "draft"

    @pytest.mark.asyncio
    async def test_synthesizes_for_selected_personas_only(self) -> None:
        """Only selected personas get synthesis — not all generated."""
        persona2 = _make_persona("p2", "VP of Engineering")
        cs = _make_company_state(selected_persona_ids=["p1"])
        cs = dict(cs)
        cs["generated_personas"] = [_make_persona("p1"), persona2]

        updated_cs, _ = await run_synthesis(
            cs=cs,  # type: ignore
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        # Only p1 selected, so only p1 should have synthesis
        assert "p1" in updated_cs["synthesis_outputs"]
        # p2 not selected
        assert "p2" not in updated_cs["synthesis_outputs"]


# ---------------------------------------------------------------------------
# Enrichment context builder tests
# ---------------------------------------------------------------------------


class TestBuildEnrichmentContext:
    def test_returns_empty_when_no_capability_map(self) -> None:
        assert _build_enrichment_context(["some_id"], None) == ""

    def test_returns_empty_when_no_matched_ids(self) -> None:
        cap_map = CapabilityMap(
            entries=[CapabilityMapEntry({"id": "x", "label": "X"})],
            version="1.0",
        )
        assert _build_enrichment_context([], cap_map) == ""

    def test_builds_context_from_matched_entries(self) -> None:
        cap_map = CapabilityMap(
            entries=[
                CapabilityMapEntry({
                    "id": "ml",
                    "label": "ML Platform",
                    "differentiators": ["Best ML ops"],
                    "sales_plays": [{"play": "ML scaling", "category": "ml"}],
                    "proof_points": [{"customer": "BigCo", "summary": "2x faster"}],
                }),
            ],
            version="1.0",
        )
        result = _build_enrichment_context(["ml"], cap_map)
        assert "ML Platform" in result
        assert "Best ML ops" in result
        assert "ML scaling" in result
        assert "BigCo" in result

    def test_skips_stale_ids(self) -> None:
        cap_map = CapabilityMap(
            entries=[CapabilityMapEntry({"id": "valid", "label": "Valid", "differentiators": ["Diff"]})],
            version="1.0",
        )
        result = _build_enrichment_context(["valid", "deleted_id"], cap_map)
        assert "Valid" in result

    def test_returns_empty_when_entries_have_no_enrichment(self) -> None:
        cap_map = CapabilityMap(
            entries=[CapabilityMapEntry({"id": "bare", "label": "Bare"})],
            version="1.0",
        )
        result = _build_enrichment_context(["bare"], cap_map)
        assert result == ""

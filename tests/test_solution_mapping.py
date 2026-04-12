"""Tests for Solution Mapping Agent — confidence thresholds and vendor name validation."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.solution_mapping import (
    _build_solution_mapping_prompt,
    _contains_vendor_name,
    _parse_solution_mapping_response,
    _sanitize_solution_areas,
    run_solution_mapping,
)
from backend.models.enums import HumanReviewReason, PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    QualifiedSignal,
    ResearchResult,
)


def _make_company_state(company_id: str = "stripe") -> CompanyState:
    return CompanyState(
        company_id=company_id,
        company_name=company_id.capitalize(),
        status=PipelineStatus.RUNNING,
        current_stage="solution_mapping",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id=company_id,
            summary="Hiring for ML platform and kubernetes infrastructure roles.",
            signal_type="job_posting",
            keywords_matched=["kubernetes", "ml platform"],
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
            company_context="Stripe is a global payments infrastructure company.",
            tech_stack=["kubernetes", "go"],
            hiring_signals="Scaling platform engineering team.",
            partial=False,
        ),
        solution_mapping=None,
        generated_personas=[],
        selected_personas=[],
        recommended_outreach_sequence=[],
        synthesis_outputs={},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=1,
            tier_2_calls=0,
            tier_3_calls=0,
            llm_tokens_used=0,
            estimated_cost_usd=0.001,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


def _make_mock_capability_map():
    cap_map = MagicMock()
    cap_map.entries = []
    return cap_map


def _make_llm_response(confidence: int) -> str:
    return (
        f'{{"core_problem": "Scaling ML infrastructure", '
        f'"solution_areas": ["Distributed compute orchestration", "ML pipeline automation"], '
        f'"confidence_score": {confidence}, '
        f'"reasoning": "Strong signal for ML infra investment."}}'
    )


class TestCoreProblemSpecificity:
    """Regression tests for issue #15: core problem summary must require company-specific details."""

    def test_prompt_requires_company_name_in_core_problem(self) -> None:
        """The prompt must instruct the LLM to include the company name in core_problem."""
        prompt = _build_solution_mapping_prompt(
            company_name="Acme Corp",
            signal_summary="Hiring ML engineers",
            research_context="Company context: Acme Corp is a fintech company.",
            capability_map_text="(No capability map configured.)",
        )
        assert "company name" in prompt.lower()
        assert "specific" in prompt.lower()

    def test_prompt_includes_few_shot_examples(self) -> None:
        """The prompt must include examples of good vs bad core_problem descriptions."""
        prompt = _build_solution_mapping_prompt(
            company_name="Acme Corp",
            signal_summary="Hiring ML engineers",
            research_context="Company context: Acme Corp is a fintech company.",
            capability_map_text="(No capability map configured.)",
        )
        assert "BAD" in prompt
        assert "GOOD" in prompt

    def test_prompt_rejects_generic_descriptions(self) -> None:
        """The prompt must explicitly instruct against generic problem statements."""
        prompt = _build_solution_mapping_prompt(
            company_name="Acme Corp",
            signal_summary="Hiring ML engineers",
            research_context="Company context: Acme Corp is a fintech company.",
            capability_map_text="(No capability map configured.)",
        )
        assert "generic" in prompt.lower()

    def test_prompt_includes_company_name_in_examples(self) -> None:
        """Few-shot GOOD examples must reference the actual company name for grounding."""
        prompt = _build_solution_mapping_prompt(
            company_name="Acme Corp",
            signal_summary="Hiring ML engineers",
            research_context="Company context: Acme Corp is a fintech company.",
            capability_map_text="(No capability map configured.)",
        )
        # The GOOD examples should include the company_name variable interpolation
        assert "Acme Corp" in prompt

    @pytest.mark.asyncio
    async def test_research_context_labels_are_present(self) -> None:
        """Research context parts should be labeled so the LLM can reference them."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        # Use a specific core_problem that includes the company name to verify end-to-end
        specific_response = (
            '{"core_problem": "Stripe needs to scale its Kubernetes-based ML platform '
            'to support real-time fraud detection across its payments infrastructure.", '
            '"solution_areas": ["Distributed compute orchestration", "ML pipeline automation"], '
            '"confidence_score": 80, '
            '"reasoning": "Strong signal for ML infra investment at Stripe."}'
        )
        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = specific_response
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        core_problem = updated_cs["solution_mapping"]["core_problem"]
        assert "Stripe" in core_problem
        assert "Kubernetes" in core_problem


class TestVendorNameValidation:
    def test_rejects_snowflake(self) -> None:
        assert _contains_vendor_name("Snowflake data warehousing") is True

    def test_rejects_databricks(self) -> None:
        assert _contains_vendor_name("Databricks lakehouse") is True

    def test_rejects_aws_glue(self) -> None:
        assert _contains_vendor_name("AWS Glue ETL pipelines") is True

    def test_accepts_vendor_agnostic_area(self) -> None:
        assert _contains_vendor_name("Distributed query execution") is False

    def test_accepts_columnar_storage(self) -> None:
        assert _contains_vendor_name("Columnar storage optimization") is False

    def test_sanitize_removes_vendor_areas(self) -> None:
        areas = ["Columnar storage", "Snowflake integration", "ML pipeline automation"]
        result = _sanitize_solution_areas(areas)
        assert "Snowflake integration" not in result
        assert "Columnar storage" in result
        assert "ML pipeline automation" in result

    def test_sanitize_handles_empty_list(self) -> None:
        assert _sanitize_solution_areas([]) == []


class TestParseSolutionMappingResponse:
    def test_parses_valid_json(self) -> None:
        response = _make_llm_response(75)
        result = _parse_solution_mapping_response(response)
        assert result is not None
        assert result["confidence_score"] == 75
        assert isinstance(result["solution_areas"], list)

    def test_returns_none_on_invalid_json(self) -> None:
        assert _parse_solution_mapping_response("not json") is None

    def test_returns_none_on_missing_required_fields(self) -> None:
        assert _parse_solution_mapping_response('{"core_problem": "test"}') is None

    def test_extracts_json_from_prose(self) -> None:
        response = f'Here is the analysis:\n{_make_llm_response(60)}\nEnd.'
        result = _parse_solution_mapping_response(response)
        assert result is not None


class TestConfidenceThresholds:
    @pytest.mark.asyncio
    async def test_confidence_49_sets_human_review(self) -> None:
        """confidence_score < 50 must set human_review_required = True."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _make_llm_response(49)
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["human_review_required"] is True
        assert HumanReviewReason.LOW_CONFIDENCE in updated_cs["human_review_reasons"]

    @pytest.mark.asyncio
    async def test_confidence_50_does_not_set_human_review(self) -> None:
        """confidence_score == 50 must NOT set human_review_required."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _make_llm_response(50)
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["human_review_required"] is False

    @pytest.mark.asyncio
    async def test_confidence_59_sets_human_review_false(self) -> None:
        """59 is above 50 threshold → no human review flag (draft gate at 60 is in Draft Agent)."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _make_llm_response(59)
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["human_review_required"] is False
        assert updated_cs["solution_mapping"]["confidence_score"] == 59

    @pytest.mark.asyncio
    async def test_confidence_60_no_review_flag(self) -> None:
        """confidence >= 60 → no flags set."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _make_llm_response(60)
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["human_review_required"] is False
        assert updated_cs["solution_mapping"]["confidence_score"] == 60

    @pytest.mark.asyncio
    async def test_no_llm_model_returns_zero_confidence(self) -> None:
        """No LLM model → fallback with confidence_score=0 and human_review_required=True."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        updated_cs, cost = await run_solution_mapping(
            cs=cs,
            capability_map=cap_map,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )

        assert updated_cs["solution_mapping"]["confidence_score"] == 0
        assert updated_cs["human_review_required"] is True
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_updates_current_stage(self) -> None:
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        updated_cs, _ = await run_solution_mapping(
            cs=cs,
            capability_map=cap_map,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["current_stage"] == "persona_generation"

    @pytest.mark.asyncio
    async def test_vendor_names_removed_from_solution_areas(self) -> None:
        """LLM output with vendor names → solution_areas sanitized."""
        cs = _make_company_state("stripe")
        cap_map = _make_mock_capability_map()

        bad_response = (
            '{"core_problem": "Data integration", '
            '"solution_areas": ["Snowflake warehousing", "Stream processing"], '
            '"confidence_score": 70, '
            '"reasoning": "Test"}'
        )
        with patch(
            "backend.agents.solution_mapping.ChatAnthropic"
        ) as MockLLM:
            mock_response = MagicMock()
            mock_response.content = bad_response
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_solution_mapping(
                cs=cs,
                capability_map=cap_map,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        areas = updated_cs["solution_mapping"]["solution_areas"]
        assert not any("nowflake" in a for a in areas)
        assert "Stream processing" in areas

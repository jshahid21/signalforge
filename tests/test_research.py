"""Tests for Research Agent — graceful degradation and partial flag behavior."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.research import _run_tech_stack_extraction, run_research
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    QualifiedSignal,
    RawSignal,
)


def _make_company_state(company_id: str = "stripe") -> CompanyState:
    return CompanyState(
        company_id=company_id,
        company_name=company_id.capitalize(),
        status=PipelineStatus.RUNNING,
        current_stage="research",
        raw_signals=[
            RawSignal(
                source="jsearch",
                signal_type="job_posting",
                content="Senior Kubernetes Engineer — platform engineering",
                url=None,
                published_at=None,
                tier=SignalTier.TIER_1,
            )
        ],
        qualified_signal=QualifiedSignal(
            company_id=company_id,
            summary="Hiring for platform engineering and kubernetes roles.",
            signal_type="job_posting",
            keywords_matched=["kubernetes"],
            deterministic_score=0.6,
            llm_severity_score=0.7,
            composite_score=0.66,
            tier_used=SignalTier.TIER_1,
            raw_signals=[],
            qualified=True,
            disqualification_reason=None,
            partial=False,
            signal_ambiguity_score=0.3,
        ),
        signal_qualified=True,
        research_result=None,
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


_LLM_RESPONSE_MOCK = "Company context here."
_TECH_STACK_MOCK = '["kubernetes", "terraform"]'
_HIRING_MOCK = "Hiring for platform engineering roles."


class TestRunResearch:
    @pytest.mark.asyncio
    async def test_runs_with_no_llm_configured(self) -> None:
        """No LLM model → all sub-tasks return None/[] gracefully."""
        cs = _make_company_state("stripe")
        updated_cs, cost = await run_research(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        result = updated_cs["research_result"]
        assert result is not None
        assert result["company_context"] is None
        assert result["tech_stack"] == []
        assert result["hiring_signals"] is None
        assert result["partial"] is True
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_partial_true_when_any_subtask_fails(self) -> None:
        """If any sub-task raises an exception, partial=True is set."""
        cs = _make_company_state("stripe")

        def _raise(*args, **kwargs):
            raise RuntimeError("LLM error")

        with patch(
            "backend.agents.research._run_company_context",
            new=AsyncMock(side_effect=RuntimeError("LLM error")),
        ):
            updated_cs, _ = await run_research(
                cs=cs,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        result = updated_cs["research_result"]
        assert result["partial"] is True

    @pytest.mark.asyncio
    async def test_all_subtasks_succeed(self) -> None:
        """All sub-tasks succeed → partial=False, all fields populated."""
        cs = _make_company_state("stripe")

        with (
            patch(
                "backend.agents.research._run_company_context",
                new=AsyncMock(return_value="Stripe is a payment infrastructure company."),
            ),
            patch(
                "backend.agents.research._run_tech_stack_extraction",
                new=AsyncMock(return_value=["kubernetes", "go"]),
            ),
            patch(
                "backend.agents.research._run_hiring_signal_analysis",
                new=AsyncMock(return_value="Hiring for platform and data engineering."),
            ),
        ):
            updated_cs, cost = await run_research(
                cs=cs,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        result = updated_cs["research_result"]
        assert result["company_context"] == "Stripe is a payment infrastructure company."
        assert result["tech_stack"] == ["kubernetes", "go"]
        assert result["hiring_signals"] == "Hiring for platform and data engineering."
        assert result["partial"] is False
        assert cost > 0

    @pytest.mark.asyncio
    async def test_updates_current_stage(self) -> None:
        cs = _make_company_state("stripe")
        updated_cs, _ = await run_research(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["current_stage"] == "solution_mapping"

    @pytest.mark.asyncio
    async def test_partial_true_when_company_context_none_with_llm(self) -> None:
        """LLM configured but context returns None → partial=True."""
        cs = _make_company_state("stripe")

        with (
            patch(
                "backend.agents.research._run_company_context",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "backend.agents.research._run_tech_stack_extraction",
                new=AsyncMock(return_value=["kubernetes"]),
            ),
            patch(
                "backend.agents.research._run_hiring_signal_analysis",
                new=AsyncMock(return_value=None),
            ),
        ):
            updated_cs, _ = await run_research(
                cs=cs,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )

        assert updated_cs["research_result"]["partial"] is True


    @pytest.mark.asyncio
    async def test_budget_exceeded_marks_failed(self) -> None:
        """Budget exhausted before research → company FAILED with budget_exceeded error."""
        cs = _make_company_state("stripe")
        updated_cs, cost = await run_research(
            cs=cs,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=1.0,  # already at max
            max_budget_usd=1.0,
        )
        assert updated_cs["status"] == PipelineStatus.FAILED
        assert cost == 0.0
        assert any(
            e["error_type"] == "budget_exceeded" for e in updated_cs["errors"]
        )


class TestTechStackExtraction:
    @pytest.mark.asyncio
    async def test_returns_empty_list_with_no_model(self) -> None:
        result = await _run_tech_stack_extraction("kubernetes deployment", "")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_empty_content(self) -> None:
        result = await _run_tech_stack_extraction("", "claude-sonnet-4-6")
        assert result == []

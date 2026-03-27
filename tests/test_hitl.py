"""HITL (Human-in-the-Loop) integration tests — pause/resume pattern (spec §5.7, §13.3)."""
from __future__ import annotations

import pytest

from backend.agents.hitl_gate import apply_persona_selection, run_persona_selection_gate
from backend.agents.persona_generation import run_persona_generation
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    QualifiedSignal,
    ResearchResult,
    SolutionMappingOutput,
)


def _make_company_state() -> CompanyState:
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="persona_generation",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id="stripe",
            summary="Hiring Kubernetes and SRE platform engineers.",
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
            company_context="Stripe is a global payments company.",
            tech_stack=["kubernetes", "go"],
            hiring_signals="Scaling platform engineering aggressively.",
            partial=False,
        ),
        solution_mapping=SolutionMappingOutput(
            core_problem="Scaling Kubernetes infrastructure for global payments.",
            solution_areas=["Container orchestration", "Platform automation"],
            inferred_areas=[],
            confidence_score=75,
            reasoning="Strong infra signal.",
        ),
        generated_personas=[],
        selected_personas=[],
        recommended_outreach_sequence=[],
        synthesis_outputs={},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=1, tier_2_calls=0, tier_3_calls=0,
            llm_tokens_used=0, estimated_cost_usd=0.01,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


class TestRunPersonaSelectionGate:
    def test_marks_awaiting_human(self) -> None:
        cs = _make_company_state()
        result = run_persona_selection_gate(cs)
        assert result["status"] == PipelineStatus.AWAITING_HUMAN

    def test_sets_stage_to_awaiting_persona_selection(self) -> None:
        cs = _make_company_state()
        result = run_persona_selection_gate(cs)
        assert result["current_stage"] == "awaiting_persona_selection"

    def test_does_not_mutate_original(self) -> None:
        cs = _make_company_state()
        _ = run_persona_selection_gate(cs)
        assert cs["status"] == PipelineStatus.RUNNING  # original unchanged


class TestApplyPersonaSelection:
    @pytest.mark.asyncio
    async def test_applies_valid_selections(self) -> None:
        cs = _make_company_state()
        # First generate personas so we have IDs to select
        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )

        generated = cs["generated_personas"]
        assert len(generated) >= 1

        selected_ids = [p["persona_id"] for p in generated[:2]]
        updated = apply_persona_selection(cs, selected_ids)

        assert updated["selected_personas"] == selected_ids
        assert updated["current_stage"] == "synthesis"
        assert updated["status"] == PipelineStatus.RUNNING

    @pytest.mark.asyncio
    async def test_skips_unknown_persona_ids(self) -> None:
        cs = _make_company_state()
        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )

        generated = cs["generated_personas"]
        real_id = generated[0]["persona_id"]
        bad_id = "nonexistent-persona-id"

        updated = apply_persona_selection(cs, [real_id, bad_id])
        assert real_id in updated["selected_personas"]
        assert bad_id not in updated["selected_personas"]

    @pytest.mark.asyncio
    async def test_empty_selection_results_in_empty_list(self) -> None:
        cs = _make_company_state()
        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )
        updated = apply_persona_selection(cs, [])
        assert updated["selected_personas"] == []
        assert updated["current_stage"] == "synthesis"


class TestHITLPauseResumeCycle:
    """Integration tests for the full HITL pause/resume cycle (spec §13.3)."""

    @pytest.mark.asyncio
    async def test_pipeline_pauses_at_persona_gate(self) -> None:
        """company_pipeline returns AWAITING_HUMAN when no personas selected yet."""
        cs = _make_company_state()

        # Simulate persona generation step
        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )

        # Simulate the HITL gate marking (as company_pipeline does)
        if not cs.get("selected_personas"):
            cs = run_persona_selection_gate(cs)

        # Assert pipeline is now paused
        assert cs["status"] == PipelineStatus.AWAITING_HUMAN
        assert cs["current_stage"] == "awaiting_persona_selection"
        assert len(cs["generated_personas"]) >= 1

    @pytest.mark.asyncio
    async def test_resume_applies_selection_and_advances_stage(self) -> None:
        """After HITL pause, apply_persona_selection advances stage to synthesis."""
        cs = _make_company_state()

        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )
        cs = run_persona_selection_gate(cs)

        # User selects the top 2 personas
        top_2_ids = [p["persona_id"] for p in cs["generated_personas"][:2]]
        resumed_cs = apply_persona_selection(cs, top_2_ids)

        assert resumed_cs["status"] == PipelineStatus.RUNNING
        assert resumed_cs["current_stage"] == "synthesis"
        assert set(resumed_cs["selected_personas"]) == set(top_2_ids)

    @pytest.mark.asyncio
    async def test_selected_personas_enable_synthesis(self) -> None:
        """After persona selection, skip_to_synthesis condition is satisfied."""
        cs = _make_company_state()

        cs, _ = await run_persona_generation(
            cs=cs, llm_provider="", llm_model="",
            current_total_cost=0.0, max_budget_usd=1.0,
        )
        cs = run_persona_selection_gate(cs)

        selected_ids = [cs["generated_personas"][0]["persona_id"]]
        resumed_cs = apply_persona_selection(cs, selected_ids)

        # Verify skip_to_synthesis conditions are met (as checked in pipeline.py)
        already_has_selection = bool(resumed_cs.get("selected_personas"))
        stage_ok = resumed_cs.get("current_stage") in ("synthesis", "draft", "awaiting_persona_selection")
        has_qualified_signal = resumed_cs.get("qualified_signal") is not None
        has_solution_mapping = resumed_cs.get("solution_mapping") is not None

        assert already_has_selection
        assert stage_ok
        assert has_qualified_signal
        assert has_solution_mapping

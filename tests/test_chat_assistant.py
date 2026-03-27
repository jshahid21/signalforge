"""Tests for Chat Assistant Agent — context block assembly, read-only constraint."""
from __future__ import annotations

import pytest

from backend.agents.chat_assistant import _build_context_block, get_chat_response
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    Draft,
    Persona,
    QualifiedSignal,
    ResearchResult,
    SolutionMappingOutput,
    SynthesisOutput,
)


def _make_persona(persona_id: str = "p1") -> Persona:
    return Persona(
        persona_id=persona_id,
        title="Head of Platform Engineering",
        targeting_reason="Owns infra.",
        role_type="technical_buyer",
        seniority_level="director",
        priority_score=0.9,
        is_custom=False,
        is_edited=False,
    )


def _make_company_state() -> CompanyState:
    persona = _make_persona("p1")
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="done",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id="stripe",
            summary="Hiring platform engineers for kubernetes.",
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
            tech_stack=["kubernetes", "go"],
            hiring_signals="Scaling platform engineering.",
            partial=False,
        ),
        solution_mapping=SolutionMappingOutput(
            core_problem="Scaling Kubernetes for global payments.",
            solution_areas=["Container orchestration"],
            inferred_areas=[],
            confidence_score=75,
            reasoning="Strong signal.",
        ),
        generated_personas=[persona],
        selected_personas=["p1"],
        recommended_outreach_sequence=["p1"],
        synthesis_outputs={
            "p1": SynthesisOutput(
                core_pain_point="Kubernetes at capacity.",
                technical_context="Uses kubernetes.",
                solution_alignment="Container orchestration helps.",
                persona_targeting="Platform lead owns this.",
                buyer_relevance="Risk and cost.",
                value_hypothesis="Reduce incidents.",
                risk_if_ignored="SLA breaches.",
            )
        },
        drafts={
            "p1": Draft(
                draft_id="d1",
                company_id="stripe",
                persona_id="p1",
                subject_line="Kubernetes scaling at Stripe",
                body="Your platform team is hiring SRE engineers...",
                confidence_score=75.0,
                approved=False,
                version=1,
            )
        },
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


class TestBuildContextBlock:
    def test_includes_company_name(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs)
        assert "Stripe" in context

    def test_includes_signal_summary(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs)
        assert "kubernetes" in context.lower()

    def test_includes_tech_stack(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs)
        assert "kubernetes" in context.lower()
        assert "go" in context.lower()

    def test_includes_core_problem(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs)
        assert "Scaling Kubernetes" in context

    def test_includes_selected_personas(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs)
        assert "Head of Platform Engineering" in context

    def test_includes_active_draft_subject(self) -> None:
        cs = _make_company_state()
        context = _build_context_block(cs, active_persona_id="p1")
        assert "Kubernetes scaling at Stripe" in context

    def test_handles_minimal_state(self) -> None:
        """State with no research/solution/personas → no crash."""
        cs = CompanyState(
            company_id="x",
            company_name="MinimalCo",
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
                tier_1_calls=0, tier_2_calls=0, tier_3_calls=0,
                llm_tokens_used=0, estimated_cost_usd=0.0, tier_escalation_reasons=[],
            ),
            errors=[],
            human_review_required=False,
            human_review_reasons=[],
            override_requested=False,
            override_reason=None,
            drafted_under_override=False,
        )
        context = _build_context_block(cs)
        assert "MinimalCo" in context


class TestGetChatResponse:
    @pytest.mark.asyncio
    async def test_returns_error_message_without_llm(self) -> None:
        """No LLM model → returns error message (not an exception)."""
        cs = _make_company_state()
        response = await get_chat_response(
            cs=cs,
            user_message="Why was this signal qualified?",
            conversation_history=[],
            llm_model="",
        )
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_accepts_conversation_history(self) -> None:
        """Should not crash with conversation history."""
        cs = _make_company_state()
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hello! How can I help?"},
        ]
        response = await get_chat_response(
            cs=cs,
            user_message="What is the core problem?",
            conversation_history=history,
            llm_model="",
        )
        assert isinstance(response, str)

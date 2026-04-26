"""Tests for Draft Agent — confidence gate boundaries, version increment."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.draft import (
    _DRAFT_CONFIDENCE_GATE,
    _build_draft_system_prompt,
    _build_seller_intelligence_section,
    run_draft,
    run_drafts_for_company,
)
from backend.models.enums import HumanReviewReason, PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    Draft,
    Persona,
    QualifiedSignal,
    ResearchResult,
    SellerProfile,
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


def _make_synthesis(persona_id: str = "p1") -> SynthesisOutput:
    return SynthesisOutput(
        core_pain_point="Kubernetes at capacity.",
        technical_context="Uses kubernetes and go.",
        solution_alignment="Container orchestration addresses this.",
        persona_targeting="Owns platform infra decisions.",
        buyer_relevance="Operational risk and cost efficiency.",
        value_hypothesis="Reduce incidents by 40%.",
        risk_if_ignored="SLA breaches at scale.",
    )


def _make_company_state(
    confidence_score: int = 75,
    selected_persona_ids: list[str] | None = None,
    override_requested: bool = False,
) -> CompanyState:
    persona = _make_persona("p1")
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="draft",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id="stripe",
            summary="Hiring platform engineers.",
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
        solution_mapping=SolutionMappingOutput(
            core_problem="Scaling Kubernetes for global payments.",
            solution_areas=["Container orchestration"],
            inferred_areas=[],
            confidence_score=confidence_score,
            reasoning="Strong infra signal.",
        ),
        generated_personas=[persona],
        selected_personas=selected_persona_ids if selected_persona_ids is not None else ["p1"],
        recommended_outreach_sequence=["p1"],
        synthesis_outputs={"p1": _make_synthesis("p1")},
        drafts={},
        cost_metadata=CostMetadata(
            tier_1_calls=1, tier_2_calls=0, tier_3_calls=0,
            llm_tokens_used=0, estimated_cost_usd=0.01,
            tier_escalation_reasons=[],
        ),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=override_requested,
        override_reason=None,
        drafted_under_override=False,
    )


_DRAFT_MOCK_RESPONSE = '{"subject": "Kubernetes scaling at Stripe — platform engineering signal", "body": "Your platform team is hiring aggressively for SRE and Kubernetes roles, a clear signal of infrastructure investment..."}'

_SELLER_PROFILE = SellerProfile(
    company_name="CloudCo",
    portfolio_summary="Cloud infrastructure tooling",
    portfolio_items=["Kubernetes Optimizer", "Cost Analyzer"],
)


class TestConfidenceGateBoundary:
    @pytest.mark.asyncio
    async def test_confidence_34_skips_draft(self) -> None:
        """confidence_score = 34 (< 35) → draft NOT generated (hard gate)."""
        cs = _make_company_state(confidence_score=34)
        persona = _make_persona("p1")

        draft, cost = await run_draft(
            cs=cs,
            persona=persona,
            seller_profile=_SELLER_PROFILE,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert draft is None
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_confidence_59_generates_hedged_draft(self) -> None:
        """confidence_score = 59 (35 ≤ x < 60) → hedged draft IS generated."""
        cs = _make_company_state(confidence_score=59)
        persona = _make_persona("p1")

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, cost = await run_draft(
                cs=cs,
                persona=persona,
                seller_profile=_SELLER_PROFILE,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )
        assert draft is not None
        assert cost > 0

    @pytest.mark.asyncio
    async def test_confidence_60_generates_draft(self) -> None:
        """confidence_score = 60 (≥ 60) → draft generated."""
        cs = _make_company_state(confidence_score=60)
        persona = _make_persona("p1")

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, cost = await run_draft(
                cs=cs,
                persona=persona,
                seller_profile=_SELLER_PROFILE,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )
        assert draft is not None
        assert draft["subject_line"]
        assert draft["body"]
        assert cost > 0

    @pytest.mark.asyncio
    async def test_confidence_threshold_constant_is_35(self) -> None:
        assert _DRAFT_CONFIDENCE_GATE == 35

    @pytest.mark.asyncio
    async def test_override_generates_draft_even_below_threshold(self) -> None:
        """override_requested = True → draft generated despite confidence < 60."""
        cs = _make_company_state(confidence_score=45, override_requested=True)
        persona = _make_persona("p1")

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, cost = await run_draft(
                cs=cs,
                persona=persona,
                seller_profile=_SELLER_PROFILE,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )
        assert draft is not None


class TestVersionIncrement:
    @pytest.mark.asyncio
    async def test_first_draft_version_is_1(self) -> None:
        cs = _make_company_state(confidence_score=75)
        persona = _make_persona("p1")

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, _ = await run_draft(
                cs=cs,
                persona=persona,
                seller_profile=None,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
                existing_draft=None,
            )
        assert draft is not None
        assert draft["version"] == 1

    @pytest.mark.asyncio
    async def test_regeneration_increments_version(self) -> None:
        """Passing existing_draft with version=1 → new draft has version=2."""
        cs = _make_company_state(confidence_score=75)
        persona = _make_persona("p1")
        existing = Draft(
            draft_id="old-id",
            company_id="stripe",
            persona_id="p1",
            subject_line="Old subject",
            body="Old body",
            confidence_score=75.0,
            approved=False,
            version=1,
        )

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, _ = await run_draft(
                cs=cs,
                persona=persona,
                seller_profile=None,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
                existing_draft=existing,
            )
        assert draft is not None
        assert draft["version"] == 2

    @pytest.mark.asyncio
    async def test_version_increments_from_any_number(self) -> None:
        cs = _make_company_state(confidence_score=75)
        persona = _make_persona("p1")
        existing = Draft(
            draft_id="x", company_id="stripe", persona_id="p1",
            subject_line="", body="", confidence_score=75.0,
            approved=False, version=5,
        )
        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            draft, _ = await run_draft(
                cs=cs, persona=persona, seller_profile=None,
                llm_provider="anthropic", llm_model="claude-sonnet-4-6",
                current_total_cost=0.0, max_budget_usd=1.0, existing_draft=existing,
            )
        assert draft is not None
        assert draft["version"] == 6


class TestRunDraftsForCompany:
    @pytest.mark.asyncio
    async def test_confidence_30_flags_human_review_required(self) -> None:
        """run_drafts_for_company: confidence < 35 → human_review_required=True, no draft."""
        cs = _make_company_state(confidence_score=30)

        updated_cs, cost = await run_drafts_for_company(
            cs=cs,
            seller_profile=None,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["human_review_required"] is True
        assert HumanReviewReason.LOW_CONFIDENCE in updated_cs["human_review_reasons"]
        assert cost == 0.0

    @pytest.mark.asyncio
    async def test_confidence_45_generates_hedged_draft_no_review(self) -> None:
        """run_drafts_for_company: 35 ≤ confidence < 60 → hedged draft, no hard-gate review."""
        cs = _make_company_state(confidence_score=45, selected_persona_ids=["p1"])
        cs = dict(cs)
        cs["generated_personas"] = [_make_persona("p1")]
        cs["synthesis_outputs"] = {"p1": _make_synthesis("p1")}

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, cost = await run_drafts_for_company(
                cs=cs,  # type: ignore[arg-type]
                seller_profile=None,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )
        assert updated_cs.get("low_confidence_draft") is True
        assert "p1" in updated_cs["drafts"]
        assert cost > 0

    @pytest.mark.asyncio
    async def test_parallel_drafts_respect_session_budget(self) -> None:
        """Regression for issue #8 bug 3: parallel drafts must not exceed
        the session budget by dispatching N concurrent LLM calls against the
        same snapshot of current_total_cost.

        Five personas, budget for only ~2 drafts. The implementation must cap
        the number of concurrent drafts so the total draft cost never exceeds
        what the budget could afford.
        """
        from backend.agents.draft import _LLM_COST

        persona_ids = [f"p{i}" for i in range(1, 6)]
        personas = [_make_persona(pid) for pid in persona_ids]
        cs = _make_company_state(confidence_score=80, selected_persona_ids=persona_ids)
        cs = dict(cs)
        cs["generated_personas"] = personas
        cs["synthesis_outputs"] = {pid: _make_synthesis(pid) for pid in persona_ids}

        # Budget for exactly 2 drafts (+ a tiny buffer to avoid float edge cases)
        max_budget = 2 * _LLM_COST + 1e-9
        current_total = 0.0

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, total_cost = await run_drafts_for_company(
                cs=cs,  # type: ignore[arg-type]
                seller_profile=None,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=current_total,
                max_budget_usd=max_budget,
            )

        # Must never exceed the session budget
        assert current_total + total_cost <= max_budget + 1e-9
        # Must draft at most floor(budget / _LLM_COST) = 2 personas
        assert len(updated_cs["drafts"]) <= 2

    @pytest.mark.asyncio
    async def test_override_tags_drafted_under_override(self) -> None:
        """override_requested=True + confidence < 35 → drafted_under_override=True."""
        cs = _make_company_state(confidence_score=25, override_requested=True)

        with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
            mock_response = MagicMock()
            mock_response.content = _DRAFT_MOCK_RESPONSE
            MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

            updated_cs, _ = await run_drafts_for_company(
                cs=cs,
                seller_profile=None,
                llm_provider="anthropic",
                llm_model="claude-sonnet-4-6",
                current_total_cost=0.0,
                max_budget_usd=1.0,
            )
        assert updated_cs["drafted_under_override"] is True


# ---------------------------------------------------------------------------
# Seller intelligence enrichment tests
# ---------------------------------------------------------------------------

_SELLER_PROFILE_WITH_INTELLIGENCE = SellerProfile(
    company_name="CloudCo",
    portfolio_summary="Cloud infrastructure tooling",
    portfolio_items=["Kubernetes Optimizer", "Cost Analyzer"],
    seller_intelligence={
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
        "last_scraped": "2026-04-12T00:00:00Z",
    },
)


class TestBuildSellerIntelligenceSection:
    def test_returns_empty_when_no_intelligence(self) -> None:
        profile = SellerProfile(
            company_name="TestCo",
            portfolio_summary="",
            portfolio_items=[],
        )
        assert _build_seller_intelligence_section(profile) == ""

    def test_returns_empty_when_intelligence_is_empty(self) -> None:
        profile = SellerProfile(
            company_name="TestCo",
            portfolio_summary="",
            portfolio_items=[],
            seller_intelligence={
                "differentiators": [],
                "sales_plays": [],
                "proof_points": [],
                "competitive_positioning": [],
            },
        )
        assert _build_seller_intelligence_section(profile) == ""

    def test_includes_all_categories(self) -> None:
        section = _build_seller_intelligence_section(_SELLER_PROFILE_WITH_INTELLIGENCE)
        assert "## Seller Intelligence" in section
        assert "Best-in-class ML ops platform" in section
        assert "FinOps cost optimization" in section
        assert "cost_optimization" in section
        assert "Acme Corp" in section
        assert "Reduced cloud costs by 40%" in section
        assert "real-time model monitoring" in section

    def test_includes_selection_instructions(self) -> None:
        section = _build_seller_intelligence_section(_SELLER_PROFILE_WITH_INTELLIGENCE)
        assert "1-2 most compelling" in section
        assert "select the 1 most relevant" in section

    def test_partial_intelligence_only_includes_present(self) -> None:
        profile = SellerProfile(
            company_name="TestCo",
            portfolio_summary="",
            portfolio_items=[],
            seller_intelligence={
                "differentiators": ["Unique feature"],
                "sales_plays": [],
                "proof_points": [],
                "competitive_positioning": [],
            },
        )
        section = _build_seller_intelligence_section(profile)
        assert "Unique feature" in section
        assert "Sales plays" not in section
        assert "Proof points" not in section


class TestDraftSystemPromptWithIntelligence:
    def test_prompt_includes_intelligence_when_available(self) -> None:
        prompt = _build_draft_system_prompt(_SELLER_PROFILE_WITH_INTELLIGENCE, [])
        assert "## Seller Intelligence" in prompt
        assert "FinOps cost optimization" in prompt
        assert "Acme Corp" in prompt
        assert "CloudCo" in prompt

    def test_prompt_fallback_without_intelligence(self) -> None:
        prompt = _build_draft_system_prompt(_SELLER_PROFILE, [])
        assert "## Seller Intelligence" not in prompt
        assert "CloudCo" in prompt
        assert "Kubernetes Optimizer" in prompt

    def test_prompt_fallback_without_profile(self) -> None:
        prompt = _build_draft_system_prompt(None, [])
        assert "vendor-agnostic" in prompt
        assert "## Seller Intelligence" not in prompt

    def test_prompt_stays_within_reasonable_length(self) -> None:
        prompt = _build_draft_system_prompt(_SELLER_PROFILE_WITH_INTELLIGENCE, [])
        # Catches runaway growth (e.g. an intelligence/persona field accidentally
        # interpolated unbounded). The system prompt was overhauled for tone and
        # 3-sentence structure; current size is ~3.2K and should not exceed ~5K
        # without an intentional design change.
        assert len(prompt) < 5000

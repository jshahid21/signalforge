"""Tests for Persona Generation Agent — signal→persona bias rules (spec §5.6)."""
from __future__ import annotations

import pytest

from backend.agents.persona_generation import (
    _classify_signal,
    _compute_outreach_sequence,
    run_persona_generation,
)
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    QualifiedSignal,
    ResearchResult,
    SolutionMappingOutput,
)


def _make_company_state(
    signal_summary: str = "Hiring for kubernetes platform engineering.",
    signal_type: str = "job_posting",
    core_problem: str = "Scaling Kubernetes infrastructure.",
    solution_areas: list[str] | None = None,
    confidence_score: int = 75,
) -> CompanyState:
    if solution_areas is None:
        solution_areas = ["Container orchestration", "Platform engineering"]
    return CompanyState(
        company_id="stripe",
        company_name="Stripe",
        status=PipelineStatus.RUNNING,
        current_stage="persona_generation",
        raw_signals=[],
        qualified_signal=QualifiedSignal(
            company_id="stripe",
            summary=signal_summary,
            signal_type=signal_type,
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
        research_result=ResearchResult(
            company_context="Stripe is a payments company.",
            tech_stack=["kubernetes"],
            hiring_signals="Hiring platform engineers.",
            partial=False,
        ),
        solution_mapping=SolutionMappingOutput(
            core_problem=core_problem,
            solution_areas=solution_areas,
            confidence_score=confidence_score,
            reasoning="Strong infra signal.",
        ),
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


class TestSignalClassification:
    def test_ml_ai_classification(self) -> None:
        category = _classify_signal("Hiring ML platform engineers tensorflow", [], "job_posting")
        assert category == "ml_ai"

    def test_infra_scaling_classification(self) -> None:
        category = _classify_signal("Scaling kubernetes platform engineering", [], "job_posting")
        assert category == "infra_scaling"

    def test_cost_optimization_classification(self) -> None:
        category = _classify_signal("FinOps cloud cost optimization initiative", [], "job_posting")
        assert category == "cost_optimization"

    def test_security_classification(self) -> None:
        category = _classify_signal("SOC2 security compliance audit", [], "engineering_blog")
        assert category == "security_compliance"

    def test_hiring_engineering_default_for_job_posting(self) -> None:
        category = _classify_signal("Backend software engineer position", [], "job_posting")
        assert category == "hiring_engineering"

    def test_default_for_unclassified(self) -> None:
        category = _classify_signal("General company update", [], "engineering_blog")
        assert category == "default"

    def test_solution_areas_contribute_to_classification(self) -> None:
        # ML keyword in solution areas should trigger ml_ai
        category = _classify_signal("Hiring engineers", ["ML pipeline automation"], "job_posting")
        assert category == "ml_ai"


class TestPersonaBiasRules:
    @pytest.mark.asyncio
    async def test_ml_signal_produces_head_of_ai_ml_platform_ml_engineer(self) -> None:
        """spec §5.6: ML/AI signals → Head of AI + ML Platform Lead + Senior ML Engineer."""
        cs = _make_company_state(
            signal_summary="Hiring ML infra engineers tensorflow pytorch",
            signal_type="job_posting",
            solution_areas=["ML pipeline automation"],
        )
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        personas = updated_cs["generated_personas"]
        titles = [p["title"] for p in personas]

        assert any("Head of AI" in t for t in titles), f"Expected 'Head of AI' in {titles}"
        assert any("ML Platform Lead" in t for t in titles), f"Expected 'ML Platform Lead' in {titles}"
        assert any("ML Engineer" in t for t in titles), f"Expected 'ML Engineer' in {titles}"

    @pytest.mark.asyncio
    async def test_ml_signal_role_types_correct(self) -> None:
        """Head of AI = economic_buyer, ML Platform Lead = technical_buyer."""
        cs = _make_company_state(
            signal_summary="Head of AI machine learning platform",
            solution_areas=["ML pipeline automation"],
        )
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        personas = updated_cs["generated_personas"]
        head_of_ai = next(p for p in personas if "Head of AI" in p["title"])
        ml_lead = next(p for p in personas if "ML Platform Lead" in p["title"])
        ml_eng = next(p for p in personas if "ML Engineer" in p["title"])

        assert head_of_ai["role_type"] == "economic_buyer"
        assert ml_lead["role_type"] == "technical_buyer"
        assert ml_eng["role_type"] == "influencer"

    @pytest.mark.asyncio
    async def test_infra_signal_produces_technical_and_economic_buyer(self) -> None:
        """spec §5.6: Infra scaling → Technical Buyer + Economic Buyer."""
        cs = _make_company_state(
            signal_summary="Kubernetes multi-region platform engineering SRE",
            solution_areas=["Container orchestration"],
        )
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        personas = updated_cs["generated_personas"]
        role_types = {p["role_type"] for p in personas}

        assert "technical_buyer" in role_types
        assert "economic_buyer" in role_types

    @pytest.mark.asyncio
    async def test_cost_optimization_produces_finops_persona(self) -> None:
        """spec §5.6: Cost optimization → Economic Buyer + FinOps Influencer."""
        cs = _make_company_state(
            signal_summary="Cloud cost optimization finops program",
            solution_areas=["Cloud cost governance"],
        )
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        personas = updated_cs["generated_personas"]
        titles = [p["title"] for p in personas]

        assert any("FinOps" in t for t in titles), f"Expected FinOps persona in {titles}"

    @pytest.mark.asyncio
    async def test_security_signal_produces_blocker(self) -> None:
        """spec §5.6: Security/compliance → Blocker + Economic Buyer."""
        cs = _make_company_state(
            signal_summary="SOC2 compliance security audit zero trust",
            solution_areas=["Security posture management"],
        )
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        personas = updated_cs["generated_personas"]
        role_types = [p["role_type"] for p in personas]

        assert "blocker" in role_types

    @pytest.mark.asyncio
    async def test_personas_have_required_fields(self) -> None:
        cs = _make_company_state()
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        for persona in updated_cs["generated_personas"]:
            assert "persona_id" in persona
            assert "title" in persona
            assert "role_type" in persona
            assert "seniority_level" in persona
            assert "priority_score" in persona
            assert persona["is_custom"] is False

    @pytest.mark.asyncio
    async def test_recommended_sequence_populated(self) -> None:
        cs = _make_company_state()
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        sequence = updated_cs["recommended_outreach_sequence"]
        personas = updated_cs["generated_personas"]
        persona_ids = {p["persona_id"] for p in personas}

        assert len(sequence) > 0
        assert all(pid in persona_ids for pid in sequence)

    @pytest.mark.asyncio
    async def test_stage_updated_to_awaiting_persona_selection(self) -> None:
        cs = _make_company_state()
        updated_cs, _ = await run_persona_generation(
            cs=cs,
            llm_provider="",
            llm_model="",
            current_total_cost=0.0,
            max_budget_usd=1.0,
        )
        assert updated_cs["current_stage"] == "awaiting_persona_selection"


class TestOutreachSequencing:
    def test_ml_signal_technical_buyer_leads(self) -> None:
        """Technical signals: technical_buyer or influencer should come before economic_buyer."""
        from backend.agents.persona_generation import _build_personas_for_category

        personas = _build_personas_for_category("ml_ai", "ML infra problem", [], "stripe")
        sequence = _compute_outreach_sequence(personas, "ml_ai")

        # Find the role_type for each position in sequence
        persona_by_id = {p["persona_id"]: p for p in personas}
        sequence_roles = [persona_by_id[pid]["role_type"] for pid in sequence]

        # First persona should be technical_buyer or influencer, not economic_buyer/exec alone
        assert sequence_roles[0] in ("technical_buyer", "influencer")

    def test_cost_optimization_economic_buyer_leads(self) -> None:
        """Cost optimization: economic_buyer should lead the sequence."""
        from backend.agents.persona_generation import _build_personas_for_category

        personas = _build_personas_for_category("cost_optimization", "Cost problem", [], "stripe")
        sequence = _compute_outreach_sequence(personas, "cost_optimization")

        persona_by_id = {p["persona_id"]: p for p in personas}
        first_role = persona_by_id[sequence[0]]["role_type"]
        assert first_role == "economic_buyer"

    def test_security_blocker_leads(self) -> None:
        """Security signals: blocker must be first in the sequence."""
        from backend.agents.persona_generation import _build_personas_for_category

        personas = _build_personas_for_category("security_compliance", "Security problem", [], "stripe")
        sequence = _compute_outreach_sequence(personas, "security_compliance")

        persona_by_id = {p["persona_id"]: p for p in personas}
        first_role = persona_by_id[sequence[0]]["role_type"]
        assert first_role == "blocker"

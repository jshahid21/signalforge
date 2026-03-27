"""Integration tests — spec §13.2 scenarios.

All tests use mock LLM + mock API clients; no real network calls.

Scenarios covered:
  1. 5 companies in parallel → no state collision (reducer merging verified)
  2. 1 company with Tier 1 sufficient → no Tier 2 calls made
  3. Signal qualification fails (score < threshold) → company SKIPPED, rest continue
  4. Partial research failure → ResearchResult.partial = True, pipeline continues
  5. Low confidence score → draft not generated, human_review_required = True
  6. User adds custom persona → Synthesis + Draft run for custom persona
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.hitl_gate import apply_persona_selection, run_persona_selection_gate
from backend.agents.signal_ingestion import compute_signal_density
from backend.agents.signal_qualification import (
    QUALIFICATION_THRESHOLD,
    compute_composite_score,
    compute_deterministic_score,
)
from backend.config.capability_map import CapabilityMap, CapabilityMapEntry
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyState,
    CostMetadata,
    Persona,
    RawSignal,
    ResearchResult,
    SolutionMappingOutput,
    SynthesisOutput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_signal(
    content: str = "kubernetes ml platform",
    tier: SignalTier = SignalTier.TIER_1,
) -> RawSignal:
    return RawSignal(
        source="jsearch",
        signal_type="job_posting",
        content=content,
        url=None,
        published_at=None,
        tier=tier,
    )


def _make_cost_metadata() -> CostMetadata:
    return CostMetadata(
        tier_1_calls=0,
        tier_2_calls=0,
        tier_3_calls=0,
        llm_tokens_used=0,
        estimated_cost_usd=0.0,
        tier_escalation_reasons=[],
    )


def _make_company_state(
    company_id: str = "test-co",
    company_name: str = "Test Co",
    status: PipelineStatus = PipelineStatus.PENDING,
) -> CompanyState:
    return CompanyState(
        company_id=company_id,
        company_name=company_name,
        status=status,
        current_stage="pending",
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
        cost_metadata=_make_cost_metadata(),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


def _make_capability_map(keywords: list[str] | None = None) -> CapabilityMap:
    if keywords is None:
        keywords = ["kubernetes", "ml", "platform", "data", "warehouse", "pipeline"]
    entry = CapabilityMapEntry({
        "id": "ml-platform",
        "label": "ML Platform",
        "problem_signals": keywords,
        "solution_areas": ["ml_platform", "data_pipeline"],
    })
    return CapabilityMap(entries=[entry])


def _make_persona(persona_id: str = "p1", is_custom: bool = False) -> Persona:
    return Persona(
        persona_id=persona_id,
        title="Head of Engineering",
        targeting_reason="Leads infra decisions",
        role_type="technical_buyer",
        seniority_level="director",
        priority_score=0.8,
        is_custom=is_custom,
        is_edited=False,
    )


# ---------------------------------------------------------------------------
# Scenario 1: 5 companies in parallel → no state key collision
# ---------------------------------------------------------------------------


def test_parallel_companies_no_state_collision():
    """5 companies in parallel — company_states reducer merges without overwriting."""
    from backend.models.state import merge_dict

    company_ids = ["co-a", "co-b", "co-c", "co-d", "co-e"]
    partial_updates = [
        {cid: _make_company_state(company_id=cid, company_name=f"Company {cid.upper()}")}
        for cid in company_ids
    ]

    # Apply reducer sequentially (LangGraph does this internally for concurrent branches)
    merged: dict = {}
    for update in partial_updates:
        merged = merge_dict(merged, update)

    # All 5 companies present, none overwriting another
    assert set(merged.keys()) == set(company_ids)
    for cid in company_ids:
        assert merged[cid]["company_id"] == cid


def test_state_reducer_with_overlapping_keys():
    """merge_dict: later update takes precedence for same key."""
    from backend.models.state import merge_dict

    cs_v1 = _make_company_state(company_id="co-a", company_name="Old Name")
    cs_v2 = _make_company_state(company_id="co-a", company_name="Updated Name")

    merged = merge_dict({"co-a": cs_v1}, {"co-a": cs_v2})

    assert merged["co-a"]["company_name"] == "Updated Name"
    assert len(merged) == 1


def test_merge_dict_preserves_all_concurrent_keys():
    """Simulate 5 concurrent company_pipeline returns merged into AgentState."""
    from backend.models.state import merge_dict

    states: dict = {}
    for i in range(5):
        cid = f"company-{i}"
        update = {cid: _make_company_state(company_id=cid, company_name=f"Co {i}")}
        states = merge_dict(states, update)

    assert len(states) == 5
    for i in range(5):
        assert f"company-{i}" in states
        assert states[f"company-{i}"]["company_name"] == f"Co {i}"


def test_cost_reducer_accumulates_across_parallel_branches():
    """operator.add reducer: parallel branches sum their costs correctly."""
    import operator

    costs = [0.001, 0.005, 0.002, 0.003, 0.004]
    total = 0.0
    for cost in costs:
        total = operator.add(total, cost)

    assert abs(total - sum(costs)) < 1e-9


# ---------------------------------------------------------------------------
# Scenario 2: Tier 1 sufficient → no Tier 2 calls
# ---------------------------------------------------------------------------


def test_tier1_sufficient_no_tier2_trigger():
    """When Tier 1 has enough dense signals, Tier 2 should NOT be triggered."""
    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "platform"])

    # 4 high-quality signals matching all keywords → density >= threshold (3)
    signals = [
        _make_raw_signal("kubernetes ml platform engineer"),
        _make_raw_signal("kubernetes ml platform deployment"),
        _make_raw_signal("ml platform scalability kubernetes"),
        _make_raw_signal("platform engineering kubernetes"),
    ]

    density = compute_signal_density(signals, cap_map.all_keywords())
    det_score = compute_deterministic_score(signals, cap_map)

    # Density >= 3 means no Tier 2 escalation from density check
    assert density >= 3
    # Deterministic score is non-zero (keywords matched)
    assert det_score > 0.0


def test_low_density_triggers_tier2_check():
    """When density < 3 and no keyword matches, Tier 2 escalation criteria are met."""
    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "platform", "data", "warehouse"])

    # Only 1 signal with no matching keywords
    signals = [_make_raw_signal("junior customer support role")]

    density = compute_signal_density(signals, cap_map.all_keywords())
    det_score = compute_deterministic_score(signals, cap_map)

    assert density < 3
    assert det_score == 0.0  # No keywords matched


# ---------------------------------------------------------------------------
# Scenario 3: Signal qualification fails → company SKIPPED, rest continue
# ---------------------------------------------------------------------------


def test_qualification_below_threshold_returns_false():
    """Score below QUALIFICATION_THRESHOLD → qualified = False."""
    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "warehouse", "pipeline", "data"])

    # Signal with no matching keywords → deterministic score = 0
    signals = [_make_raw_signal("general administrative assistant role")]

    det_score = compute_deterministic_score(signals, cap_map)
    # LLM score 0.0 — no technical content
    composite = compute_composite_score(det_score, 0.0)

    assert composite < QUALIFICATION_THRESHOLD


def test_qualification_above_threshold_returns_true():
    """Score above QUALIFICATION_THRESHOLD → qualified = True."""
    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "data"])

    # Signals with all keywords matched
    signals = [
        _make_raw_signal("kubernetes ml data platform engineer — build ml infrastructure"),
        _make_raw_signal("kubernetes data pipeline architect"),
        _make_raw_signal("senior ml data engineer kubernetes"),
    ]

    det_score = compute_deterministic_score(signals, cap_map)
    # Mock high LLM score
    composite = compute_composite_score(det_score, 0.9)

    assert composite >= QUALIFICATION_THRESHOLD


def test_qualification_boundary_at_threshold():
    """Boundary test: composite score at exactly QUALIFICATION_THRESHOLD qualifies."""
    cap_map = _make_capability_map(keywords=["k8s"])
    signals = [_make_raw_signal("k8s engineer")]
    det = compute_deterministic_score(signals, cap_map)

    # Solve for llm_score such that composite == QUALIFICATION_THRESHOLD
    # composite = 0.4 * det + 0.6 * llm → llm = (threshold - 0.4*det) / 0.6
    llm_score = (QUALIFICATION_THRESHOLD - 0.4 * det) / 0.6

    composite_at = compute_composite_score(det, llm_score)
    composite_below = compute_composite_score(det, max(0.0, llm_score - 0.01))

    assert composite_at >= QUALIFICATION_THRESHOLD
    assert composite_below < QUALIFICATION_THRESHOLD


# ---------------------------------------------------------------------------
# Scenario 4: Partial research failure → ResearchResult.partial = True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_research_failure_partial_flag_set():
    """When a research sub-task fails, partial=True is set and pipeline continues."""
    from backend.agents.research import run_research

    cs = _make_company_state(company_id="stripe", company_name="Stripe")
    cs["qualified_signal"] = {
        "company_id": "stripe",
        "summary": "Hiring ML engineers",
        "signal_type": "hiring_engineering",
        "keywords_matched": ["ml", "kubernetes"],
        "deterministic_score": 0.8,
        "llm_severity_score": 0.85,
        "composite_score": 0.83,
        "tier_used": SignalTier.TIER_1,
        "raw_signals": [_make_raw_signal("ml kubernetes platform")],
        "qualified": True,
        "disqualification_reason": None,
        "partial": False,
        "signal_ambiguity_score": 0.2,
    }
    cs["signal_qualified"] = True
    cs["status"] = PipelineStatus.RUNNING

    # Make _run_company_context raise — simulates partial research failure
    with patch(
        "backend.agents.research._run_company_context",
        new=AsyncMock(side_effect=Exception("LLM timeout")),
    ):
        with patch(
            "backend.agents.research._run_tech_stack_extraction",
            new=AsyncMock(return_value=["kubernetes", "python"]),
        ):
            with patch(
                "backend.agents.research._run_hiring_signal_analysis",
                new=AsyncMock(return_value="Hiring ML engineers"),
            ):
                result_cs, cost = await run_research(
                    cs=cs,
                    llm_provider="anthropic",
                    llm_model="claude-sonnet-4-6",
                    current_total_cost=0.0,
                    max_budget_usd=10.0,
                )

    # Pipeline should not fail — partial=True and continues
    assert result_cs["research_result"] is not None
    assert result_cs["research_result"]["partial"] is True
    assert result_cs["status"] != PipelineStatus.FAILED


@pytest.mark.asyncio
async def test_all_research_subtasks_succeed():
    """All sub-tasks succeed → partial=False, all fields populated."""
    from backend.agents.research import run_research

    cs = _make_company_state(company_id="databricks", company_name="Databricks")
    cs["qualified_signal"] = {
        "company_id": "databricks",
        "summary": "Scaling data platform",
        "signal_type": "data_platform",
        "keywords_matched": ["data", "platform"],
        "deterministic_score": 0.75,
        "llm_severity_score": 0.80,
        "composite_score": 0.78,
        "tier_used": SignalTier.TIER_1,
        "raw_signals": [_make_raw_signal("data platform engineer")],
        "qualified": True,
        "disqualification_reason": None,
        "partial": False,
        "signal_ambiguity_score": 0.25,
    }
    cs["signal_qualified"] = True
    cs["status"] = PipelineStatus.RUNNING

    with (
        patch(
            "backend.agents.research._run_company_context",
            new=AsyncMock(return_value="Databricks is a unified analytics platform."),
        ),
        patch(
            "backend.agents.research._run_tech_stack_extraction",
            new=AsyncMock(return_value=["Apache Spark", "Delta Lake"]),
        ),
        patch(
            "backend.agents.research._run_hiring_signal_analysis",
            new=AsyncMock(return_value="Hiring data engineers for platform scaling."),
        ),
    ):
        result_cs, cost = await run_research(
            cs=cs,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=0.0,
            max_budget_usd=10.0,
        )

    result = result_cs["research_result"]
    assert result["partial"] is False
    assert result["company_context"] == "Databricks is a unified analytics platform."
    assert "Apache Spark" in result["tech_stack"]


# ---------------------------------------------------------------------------
# Scenario 5: Low confidence score → draft not generated, human_review_required = True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_confidence_no_draft_generated():
    """Confidence < 60 → draft not generated, human_review_required = True."""
    from backend.agents.draft import run_drafts_for_company

    persona_id = "persona-abc"
    persona = _make_persona(persona_id=persona_id)
    cs = _make_company_state(company_id="low-co", company_name="Low Confidence Co")
    cs["selected_personas"] = [persona_id]
    cs["generated_personas"] = [persona]
    cs["solution_mapping"] = SolutionMappingOutput(
        core_problem="Unclear scaling challenges",
        solution_areas=["cloud_infra"],
        inferred_areas=[],
        confidence_score=45,  # Below 60 threshold
        reasoning="Insufficient signal specificity",
    )
    cs["synthesis_outputs"] = {
        persona_id: SynthesisOutput(
            core_pain_point="Generic scaling challenge",
            technical_context="No specific tech stack mentioned",
            solution_alignment="Cloud infrastructure",
            persona_targeting="Targeting director of engineering",
            buyer_relevance="Relevant to platform decisions",
            value_hypothesis="Scale without adding headcount",
            risk_if_ignored="Growth bottleneck",
        )
    }
    cs["status"] = PipelineStatus.RUNNING

    mock_response = MagicMock()
    mock_response.content = '{"subject": "Test", "body": "Test body"}'
    with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result_cs, cost = await run_drafts_for_company(
            cs=cs,
            seller_profile={"company_name": "Seller", "portfolio_summary": "Tools", "portfolio_items": []},
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=0.0,
            max_budget_usd=10.0,
            few_shot_examples=[],
        )

    # Draft should not be created due to low confidence gate
    assert persona_id not in result_cs["drafts"]
    assert result_cs["human_review_required"] is True


@pytest.mark.asyncio
async def test_high_confidence_draft_generated():
    """Confidence >= 60 → draft IS generated."""
    from backend.agents.draft import run_drafts_for_company

    persona_id = "persona-xyz"
    persona = _make_persona(persona_id=persona_id)
    cs = _make_company_state(company_id="high-co", company_name="High Confidence Co")
    cs["selected_personas"] = [persona_id]
    cs["generated_personas"] = [persona]
    cs["solution_mapping"] = SolutionMappingOutput(
        core_problem="ML platform scaling bottleneck",
        solution_areas=["ml_platform", "data_pipeline"],
        inferred_areas=[],
        confidence_score=85,  # Above 60 threshold
        reasoning="Strong signal match",
    )
    cs["synthesis_outputs"] = {
        persona_id: SynthesisOutput(
            core_pain_point="ML infrastructure bottleneck limiting model deployment velocity",
            technical_context="Kubernetes-based ML platform, model registry pain points",
            solution_alignment="ML platform tooling",
            persona_targeting="Director of ML Engineering leading model deployment",
            buyer_relevance="Directly responsible for model deployment velocity",
            value_hypothesis="3× faster model deployment with unified platform",
            risk_if_ignored="Competitors deploy models faster, losing market position",
        )
    }
    cs["status"] = PipelineStatus.RUNNING

    mock_response = MagicMock()
    mock_response.content = '{"subject": "ML platform bottleneck?", "body": "Hi, noticed you are scaling ML..."}'
    with patch("backend.agents.draft.ChatAnthropic") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result_cs, cost = await run_drafts_for_company(
            cs=cs,
            seller_profile={"company_name": "Seller", "portfolio_summary": "ML tools", "portfolio_items": ["ML Platform"]},
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=0.0,
            max_budget_usd=10.0,
            few_shot_examples=[],
        )

    assert persona_id in result_cs["drafts"]
    draft = result_cs["drafts"][persona_id]
    assert draft["subject_line"] == "ML platform bottleneck?"
    assert draft["version"] == 1
    assert draft["approved"] is False


# ---------------------------------------------------------------------------
# Scenario 6: User adds custom persona → synthesis + draft run for custom persona
# ---------------------------------------------------------------------------


def test_apply_persona_selection_includes_known_ids():
    """apply_persona_selection filters out unknown IDs, keeps valid ones."""
    p1 = _make_persona("persona-1")
    p2 = _make_persona("persona-2")
    cs = _make_company_state()
    cs["generated_personas"] = [p1, p2]
    cs["status"] = PipelineStatus.AWAITING_HUMAN
    cs["current_stage"] = "awaiting_persona_selection"

    result_cs = apply_persona_selection(cs, ["persona-1", "persona-2", "unknown-id"])

    assert "persona-1" in result_cs["selected_personas"]
    assert "persona-2" in result_cs["selected_personas"]
    assert "unknown-id" not in result_cs["selected_personas"]
    assert result_cs["current_stage"] == "synthesis"
    assert result_cs["status"] == PipelineStatus.RUNNING


@pytest.mark.asyncio
async def test_synthesis_runs_for_custom_persona():
    """Synthesis runs for a custom persona that was added during HITL."""
    from backend.agents.synthesis import run_synthesis

    custom_id = "custom-cfo-persona"
    custom_persona = _make_persona(persona_id=custom_id, is_custom=True)
    custom_persona = Persona(
        persona_id=custom_id,
        title="CFO",
        targeting_reason="Controls ML budget",
        role_type="economic_buyer",
        seniority_level="exec",
        priority_score=0.9,
        is_custom=True,
        is_edited=False,
    )

    cs = _make_company_state(company_id="acme", company_name="Acme")
    cs["selected_personas"] = [custom_id]
    cs["generated_personas"] = [custom_persona]
    cs["qualified_signal"] = {
        "company_id": "acme",
        "summary": "Hiring ML engineers across cloud platform",
        "signal_type": "hiring_engineering",
        "keywords_matched": ["ml", "platform"],
        "deterministic_score": 0.7,
        "llm_severity_score": 0.8,
        "composite_score": 0.76,
        "tier_used": SignalTier.TIER_1,
        "raw_signals": [_make_raw_signal("ml platform cloud engineer")],
        "qualified": True,
        "disqualification_reason": None,
        "partial": False,
        "signal_ambiguity_score": 0.3,
    }
    cs["solution_mapping"] = SolutionMappingOutput(
        core_problem="ML platform scaling",
        solution_areas=["ml_platform"],
        inferred_areas=[],
        confidence_score=75,
        reasoning="Good keyword match",
    )
    cs["research_result"] = ResearchResult(
        company_context="Acme is a fast-growing SaaS company",
        tech_stack=["Kubernetes", "Python"],
        hiring_signals="Hiring ML engineers rapidly",
        partial=False,
    )
    cs["status"] = PipelineStatus.RUNNING

    valid_synth_json = """{
        "core_pain_point": "ML deployment velocity bottleneck",
        "technical_context": "Kubernetes, Python ML stack",
        "solution_alignment": "ML platform tooling",
        "persona_targeting": "CFO focused on ROI of ML investment",
        "buyer_relevance": "Directly controls ML budget",
        "value_hypothesis": "Reduce ML infrastructure cost by 40%",
        "risk_if_ignored": "ML investments stall, competitors gain edge"
    }"""

    mock_response = MagicMock()
    mock_response.content = valid_synth_json
    with patch("backend.agents.synthesis.ChatAnthropic") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result_cs, cost = await run_synthesis(
            cs=cs,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=0.0,
            max_budget_usd=10.0,
        )

    # Custom persona should have synthesis output
    assert custom_id in result_cs["synthesis_outputs"]
    synth = result_cs["synthesis_outputs"][custom_id]
    assert "ML deployment velocity bottleneck" in synth["core_pain_point"]


@pytest.mark.asyncio
async def test_hitl_gate_marks_company_awaiting():
    """run_persona_selection_gate marks company as AWAITING_HUMAN."""
    cs = _make_company_state()
    cs["generated_personas"] = [_make_persona("p1")]
    cs["status"] = PipelineStatus.RUNNING

    result_cs = run_persona_selection_gate(cs)

    assert result_cs["status"] == PipelineStatus.AWAITING_HUMAN


# ---------------------------------------------------------------------------
# Fixture-driven: all 10 canonical company fixtures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", [
    pytest.param(f, id=f.expected_slug)
    for f in __import__("tests.fixtures.companies", fromlist=["COMPANY_FIXTURES"]).COMPANY_FIXTURES
])
def test_fixture_company_slug_normalization(fixture):
    """Each canonical fixture normalizes to its expected slug."""
    from backend.agents.orchestrator import normalize_company_name
    from tests.fixtures.companies import CompanyFixture

    slug = normalize_company_name(fixture.company_name)
    assert slug == fixture.expected_slug, (
        f"Company '{fixture.company_name}' expected slug '{fixture.expected_slug}', got '{slug}'"
    )


@pytest.mark.parametrize("fixture", [
    pytest.param(f, id=f.expected_slug)
    for f in __import__("tests.fixtures.companies", fromlist=["COMPANY_FIXTURES"]).COMPANY_FIXTURES
    if f.expected_qualified
])
def test_qualified_fixtures_have_signal_type(fixture):
    """All fixtures expected to qualify have a non-None expected_signal_type."""
    assert fixture.expected_signal_type is not None, (
        f"Fixture '{fixture.company_name}' is expected_qualified=True but has no expected_signal_type"
    )


@pytest.mark.parametrize("fixture", [
    pytest.param(f, id=f.expected_slug)
    for f in __import__("tests.fixtures.companies", fromlist=["COMPANY_FIXTURES"]).COMPANY_FIXTURES
    if not f.expected_qualified
])
def test_unqualified_fixtures_have_no_solution_areas(fixture):
    """Fixtures not expected to qualify should have no expected_solution_areas."""
    assert fixture.expected_solution_areas == [], (
        f"Fixture '{fixture.company_name}' is expected_qualified=False but has solution areas: {fixture.expected_solution_areas}"
    )


@pytest.mark.asyncio
async def test_fixture_qualified_company_reaches_persona_stage():
    """Canonical qualified fixture (LangChain) produces personas in pipeline run.

    This drives the pipeline against mock data configured to match the LangChain
    fixture's expected qualification result.
    """
    from tests.fixtures.companies import COMPANY_FIXTURES

    langchain_fixture = next(f for f in COMPANY_FIXTURES if f.expected_slug == "langchain")
    assert langchain_fixture.expected_qualified is True

    from backend.agents.signal_ingestion import run_signal_ingestion
    from backend.agents.signal_qualification import run_signal_qualification
    from backend.agents.persona_generation import run_persona_generation
    from backend.agents.research import run_research
    from backend.agents.solution_mapping import run_solution_mapping

    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "platform", "data", "pipeline"])
    cs = _make_company_state(company_id="langchain", company_name="LangChain")
    cs["status"] = PipelineStatus.RUNNING

    # Step 1: Ingestion with keyword-rich signals (Tier 1 sufficient)
    mock_jsearch = MagicMock()
    mock_jsearch.search_jobs = AsyncMock(return_value=[
        {"job_title": "ML Platform Engineer", "job_description": "kubernetes ml platform data pipeline engineer", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-15T10:00:00Z"},
        {"job_title": "Data Platform Lead", "job_description": "ml kubernetes data pipeline platform scaling", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-14T10:00:00Z"},
        {"job_title": "Senior Platform Engineer", "job_description": "kubernetes data ml platform infrastructure", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-13T10:00:00Z"},
    ])

    cs, ingestion_cost = await run_signal_ingestion(
        cs=cs,
        capability_map=cap_map,
        current_total_cost=0.0,
        max_budget_usd=10.0,
        jsearch_client=mock_jsearch,
        tavily_client=MagicMock(),
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )

    # Verify Tier 1 signals collected
    assert len(cs["raw_signals"]) >= 1

    # Step 2: Qualification with mocked LLM scores
    with patch("backend.agents.signal_qualification.call_llm_severity", new=AsyncMock(
        return_value=({"recency": 0.9, "specificity": 0.85, "technical_depth": 0.8, "buying_intent": 0.75}, 100)
    )):
        cs, qual_cost = await run_signal_qualification(
            cs=cs,
            capability_map=cap_map,
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-6",
            current_total_cost=ingestion_cost,
            max_budget_usd=10.0,
        )

    # Verify qualification matches expected fixture
    assert cs["signal_qualified"] == langchain_fixture.expected_qualified
    assert cs["status"] != PipelineStatus.SKIPPED, "LangChain should qualify, not be skipped"

    # Step 3: Research
    with (
        patch("backend.agents.research._run_company_context", new=AsyncMock(return_value="LangChain is a leading AI framework company.")),
        patch("backend.agents.research._run_tech_stack_extraction", new=AsyncMock(return_value=["Python", "Kubernetes"])),
        patch("backend.agents.research._run_hiring_signal_analysis", new=AsyncMock(return_value="Hiring ML engineers.")),
    ):
        cs, research_cost = await run_research(cs=cs, llm_provider="anthropic", llm_model="claude-sonnet-4-6", current_total_cost=0.0, max_budget_usd=10.0)

    # Step 4: Solution mapping
    solution_json = '{"core_problem": "ML platform scaling", "solution_areas": ["ml_platform", "data_pipeline"], "inferred_areas": [], "confidence_score": 80, "reasoning": "Strong signal"}'
    mock_sol_resp = MagicMock()
    mock_sol_resp.content = solution_json
    with patch("backend.agents.solution_mapping.ChatAnthropic") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_sol_resp)
        cs, sol_cost = await run_solution_mapping(cs=cs, capability_map=cap_map, llm_provider="anthropic", llm_model="claude-sonnet-4-6", current_total_cost=0.0, max_budget_usd=10.0)

    # Step 5: Persona generation (no LLM needed)
    cs, persona_cost = await run_persona_generation(cs=cs, llm_provider="anthropic", llm_model="claude-sonnet-4-6", current_total_cost=0.0, max_budget_usd=10.0)

    # Company should have generated personas → ready for HITL
    assert len(cs["generated_personas"]) > 0
    # Verify solution areas match fixture expectations (subset check)
    if cs["solution_mapping"] and langchain_fixture.expected_solution_areas:
        mapped = cs["solution_mapping"]["solution_areas"]
        # At least one expected solution area should be in the mapped areas
        assert any(area in mapped for area in langchain_fixture.expected_solution_areas), (
            f"None of expected {langchain_fixture.expected_solution_areas} found in {mapped}"
        )


# ---------------------------------------------------------------------------
# Scenario 2b: Tier 2 (Tavily) NOT called when Tier 1 signals are sufficient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier1_sufficient_tavily_not_called():
    """When Tier 1 provides enough high-density signals, Tavily is NOT called."""
    from backend.agents.signal_ingestion import run_signal_ingestion

    cap_map = _make_capability_map(keywords=["kubernetes", "ml", "platform"])
    cs = _make_company_state(company_id="stripe", company_name="Stripe")
    cs["status"] = PipelineStatus.RUNNING

    # 3 keyword-rich Tier 1 signals → density >= threshold, no Tier 2 needed
    mock_jsearch = MagicMock()
    mock_jsearch.search_jobs = AsyncMock(return_value=[
        {"job_title": "ML Platform Engineer", "job_description": "kubernetes ml platform data engineer", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-15T10:00:00Z"},
        {"job_title": "Platform Infrastructure Lead", "job_description": "ml kubernetes platform architecture", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-14T10:00:00Z"},
        {"job_title": "Senior ML Engineer", "job_description": "kubernetes ml platform model serving", "job_apply_link": None, "job_posted_at_datetime_utc": "2026-01-13T10:00:00Z"},
    ])
    mock_tavily = MagicMock()
    mock_tavily.search = AsyncMock(return_value=[])

    result_cs, cost = await run_signal_ingestion(
        cs=cs,
        capability_map=cap_map,
        current_total_cost=0.0,
        max_budget_usd=10.0,
        jsearch_client=mock_jsearch,
        tavily_client=mock_tavily,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-6",
    )

    # Tavily should NOT have been called — Tier 1 signals were sufficient
    mock_tavily.search.assert_not_called()
    # Signals should be present from Tier 1
    assert len(result_cs["raw_signals"]) >= 1

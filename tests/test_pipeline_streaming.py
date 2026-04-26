"""Regression test for issue #29: split company_pipeline into separate nodes.

Verifies that graph.astream() emits a chunk at each stage boundary so the UI
receives real-time WebSocket progress updates instead of one final update.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.enums import PipelineStatus
from backend.models.state import AgentState
from backend.pipeline import build_pipeline


def _recent_iso(days_ago: int) -> str:
    # Tier 1 ingestion filters jobs older than 90 days from today, so fixtures
    # must be computed relative to date.today() rather than hardcoded.
    return (date.today() - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"


def _make_initial_state(company_names: list[str]) -> AgentState:
    return AgentState(
        target_companies=company_names,
        seller_profile={
            "company_name": "TestSeller",
            "portfolio_summary": "Test tools",
            "portfolio_items": ["Tool A"],
        },
        company_states={},
        pipeline_started_at="",
        pipeline_completed_at=None,
        active_company_ids=[],
        completed_company_ids=[],
        failed_company_ids=[],
        awaiting_persona_selection=False,
        awaiting_review=[],
        execution_log=[],
        total_cost_usd=0.0,
        final_drafts=[],
    )


def _mock_persona_response() -> str:
    return """[{
        "persona_id": "p1",
        "title": "CTO",
        "targeting_reason": "Tech decisions",
        "role_type": "technical_buyer",
        "seniority_level": "c_suite",
        "priority_score": 0.9,
        "is_custom": false,
        "is_edited": false
    }]"""


@pytest.mark.asyncio
async def test_astream_emits_per_stage_chunks():
    """astream() must emit separate chunks for each pipeline stage node.

    Before the fix (issue #29), the entire per-company pipeline was a single
    node, so astream() emitted only ONE chunk for all stages combined.
    After the fix, each stage is its own node and emits its own chunk.
    """
    graph = build_pipeline(checkpointer=None)
    initial_state = _make_initial_state(["TestCo"])
    config = {"configurable": {"thread_id": "streaming-test-001"}}

    mock_llm = MagicMock()
    llm_responses = [
        '{"recency": 0.9, "specificity": 0.8, "technical_depth": 0.8, "buying_intent": 0.7}',
        '{"core_problem": "Scaling bottleneck", "solution_areas": ["platform"], "inferred_areas": [], "confidence_score": 80, "reasoning": "Strong signal"}',
        _mock_persona_response(),
    ]
    resp_iter = iter(llm_responses)

    async def _ainvoke(*args, **kwargs):
        resp = MagicMock()
        try:
            resp.content = next(resp_iter)
        except StopIteration:
            resp.content = "{}"
        return resp

    mock_llm.ainvoke = _ainvoke

    jobs = [
        {"job_title": "ML Engineer", "job_description": "ml platform kubernetes data pipeline", "job_apply_link": "https://example.com/1", "job_posted_at_datetime_utc": _recent_iso(7)},
    ]

    with (
        patch("backend.tools.jsearch.JSearchClient.search_jobs", new=AsyncMock(return_value=jobs)),
        patch("backend.tools.tavily.TavilySearchClient.__init__", return_value=None),
        patch("backend.agents.signal_qualification.call_llm_severity", new=AsyncMock(return_value=({"recency": 0.9, "specificity": 0.8, "technical_depth": 0.8, "buying_intent": 0.7}, 100))),
        patch("backend.agents.solution_mapping.ChatAnthropic", new=MagicMock(return_value=mock_llm)),
        patch("backend.agents.research._run_company_context", new=AsyncMock(return_value="TestCo is a tech company.")),
        patch("backend.agents.research._run_tech_stack_extraction", new=AsyncMock(return_value=["Python", "Kubernetes"])),
        patch("backend.agents.research._run_hiring_signal_analysis", new=AsyncMock(return_value="Hiring ML engineers.")),
        patch("backend.agents.memory_agent.get_few_shot_examples", return_value=[]),
    ):
        chunk_node_names = []
        async for chunk in graph.astream(initial_state, config=config):
            chunk_node_names.extend(chunk.keys())

    # The graph must emit separate chunks for each stage node.
    # Before the fix, this would only contain: orchestrator, company_pipeline, hitl_gate
    expected_stage_nodes = {
        "signal_ingestion",
        "signal_qualification",
        "research",
        "solution_mapping",
        "persona_generation",
    }

    emitted = set(chunk_node_names)
    assert expected_stage_nodes.issubset(emitted), (
        f"Expected per-stage chunks for {expected_stage_nodes}, "
        f"but only got chunks for: {emitted}. "
        f"If 'company_pipeline' is in the set, the monolithic node was not split."
    )
    # The old monolithic node must NOT appear
    assert "company_pipeline" not in emitted, (
        "company_pipeline should not appear — it was split into per-stage nodes"
    )


@pytest.mark.asyncio
async def test_astream_tracks_stage_progression():
    """Each stage chunk must contain updated company_states with correct current_stage."""
    graph = build_pipeline(checkpointer=None)
    initial_state = _make_initial_state(["ProgressCo"])
    config = {"configurable": {"thread_id": "streaming-test-002"}}

    mock_llm = MagicMock()
    llm_responses = [
        '{"recency": 0.9, "specificity": 0.8, "technical_depth": 0.8, "buying_intent": 0.7}',
        '{"core_problem": "Scaling", "solution_areas": ["platform"], "inferred_areas": [], "confidence_score": 80, "reasoning": "Signal"}',
        _mock_persona_response(),
    ]
    resp_iter = iter(llm_responses)

    async def _ainvoke(*args, **kwargs):
        resp = MagicMock()
        try:
            resp.content = next(resp_iter)
        except StopIteration:
            resp.content = "{}"
        return resp

    mock_llm.ainvoke = _ainvoke

    jobs = [
        {"job_title": "ML Engineer", "job_description": "ml platform kubernetes data pipeline", "job_apply_link": "https://example.com/1", "job_posted_at_datetime_utc": _recent_iso(7)},
    ]

    with (
        patch("backend.tools.jsearch.JSearchClient.search_jobs", new=AsyncMock(return_value=jobs)),
        patch("backend.tools.tavily.TavilySearchClient.__init__", return_value=None),
        patch("backend.agents.signal_qualification.call_llm_severity", new=AsyncMock(return_value=({"recency": 0.9, "specificity": 0.8, "technical_depth": 0.8, "buying_intent": 0.7}, 100))),
        patch("backend.agents.solution_mapping.ChatAnthropic", new=MagicMock(return_value=mock_llm)),
        patch("backend.agents.research._run_company_context", new=AsyncMock(return_value="ProgressCo is a tech company.")),
        patch("backend.agents.research._run_tech_stack_extraction", new=AsyncMock(return_value=["Python"])),
        patch("backend.agents.research._run_hiring_signal_analysis", new=AsyncMock(return_value="Hiring engineers.")),
        patch("backend.agents.memory_agent.get_few_shot_examples", return_value=[]),
    ):
        stage_snapshots = {}
        async for chunk in graph.astream(initial_state, config=config):
            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue
                cs_map = node_output.get("company_states", {})
                if "progressco" in cs_map:
                    stage_snapshots[node_name] = cs_map["progressco"]["current_stage"]

    # After signal_ingestion, the company should have advanced to signal_qualification
    assert stage_snapshots.get("signal_ingestion") == "signal_qualification"
    # After signal_qualification, research
    assert stage_snapshots.get("signal_qualification") == "research"
    # After research, solution_mapping
    assert stage_snapshots.get("research") == "solution_mapping"
    # After solution_mapping, persona_generation
    assert stage_snapshots.get("solution_mapping") == "persona_generation"
    # After persona_generation (with HITL gate), awaiting_persona_selection
    assert stage_snapshots.get("persona_generation") == "awaiting_persona_selection"

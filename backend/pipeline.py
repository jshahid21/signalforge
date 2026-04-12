"""LangGraph StateGraph assembly for SignalForge pipeline (no agent logic here).

Graph structure:
    orchestrator
        │
        ▼
    signal_ingestion (processes all active companies in parallel)
        │
        ▼
    signal_qualification
        │
        ▼
    research
        │
        ▼
    solution_mapping
        │
        ▼
    persona_generation (+ HITL gate marking)
        │
        ▼
    hitl_gate
        │
        ▼
      END

Each stage is a separate LangGraph node so that graph.astream() emits a chunk
at every stage boundary — enabling real-time WebSocket progress updates.

Per-company parallelism within each stage is maintained via asyncio.gather().

The HITL gate is a logical pause — the pipeline returns AWAITING_HUMAN status.
Resume is triggered via the API which calls apply_persona_selection()
and re-invokes synthesis/drafts outside the graph.

Nodes are imported from backend/agents/. This module only wires the graph.
"""
from __future__ import annotations

import asyncio

from langgraph.graph import END, StateGraph

from backend.agents.hitl_gate import (
    hitl_gate_node,
    run_persona_selection_gate,
)
from backend.agents.orchestrator import orchestrator_node
from backend.agents.persona_generation import run_persona_generation
from backend.agents.research import run_research
from backend.agents.signal_ingestion import run_signal_ingestion
from backend.agents.signal_qualification import run_signal_qualification
from backend.agents.solution_mapping import run_solution_mapping
from backend.config.capability_map import load_capability_map
from backend.config.loader import load_config
from backend.models.enums import PipelineStatus
from backend.models.state import AgentState
from backend.tools.jsearch import JSearchClient
from backend.tools.tavily import TavilySearchClient


# Statuses that mean a company should not be processed further
_TERMINAL = frozenset({
    PipelineStatus.FAILED,
    PipelineStatus.SKIPPED,
    PipelineStatus.COMPLETED,
    PipelineStatus.AWAITING_HUMAN,
})

# Maps stage node name → the current_stage value a company must have to enter
_STAGE_ENTRY = {
    "signal_ingestion": "init",
    "signal_qualification": "signal_qualification",
    "research": "research",
    "solution_mapping": "solution_mapping",
    "persona_generation": "persona_generation",
}


async def _run_stage_node(
    state: AgentState, stage_name: str, stage_fn, **extra_kwargs
) -> dict:
    """Generic per-stage node: filters active companies, runs the stage, returns
    AgentState updates.

    Companies are processed in parallel via asyncio.gather(). Only companies
    whose current_stage matches the expected entry stage are processed.
    """
    expected_stage = _STAGE_ENTRY[stage_name]
    config = load_config()

    active = [
        (cid, cs)
        for cid, cs in state.get("company_states", {}).items()
        if cs.get("status") not in _TERMINAL
        and cs.get("current_stage") == expected_stage
    ]

    if not active:
        return {}

    async def _process(cid, cs):
        return cid, await stage_fn(
            cs=cs,
            current_total_cost=state.get("total_cost_usd", 0.0),
            max_budget_usd=config.session_budget.max_usd,
            llm_provider=config.api_keys.llm_provider,
            llm_model=config.api_keys.llm_model,
            **extra_kwargs,
        )

    results = await asyncio.gather(*[_process(cid, cs) for cid, cs in active])

    updated = {}
    total_cost = 0.0
    failed_ids = []
    completed_ids = []
    for cid, (cs, cost) in results:
        updated[cid] = cs
        total_cost += cost
        if cs["status"] == PipelineStatus.FAILED:
            failed_ids.append(cid)
        elif cs["status"] in (PipelineStatus.SKIPPED, PipelineStatus.COMPLETED):
            completed_ids.append(cid)

    result: dict = {"company_states": updated, "total_cost_usd": total_cost}
    if failed_ids:
        result["failed_company_ids"] = failed_ids
    if completed_ids:
        result["completed_company_ids"] = completed_ids
    return result


# ---------------------------------------------------------------------------
# Stage nodes — thin wrappers around agent functions
# ---------------------------------------------------------------------------


async def signal_ingestion_node(state: AgentState) -> dict:
    config = load_config()
    return await _run_stage_node(
        state,
        "signal_ingestion",
        run_signal_ingestion,
        capability_map=load_capability_map(),
        jsearch_client=JSearchClient(api_key=config.api_keys.jsearch),
        tavily_client=TavilySearchClient(api_key=config.api_keys.tavily),
    )


async def signal_qualification_node(state: AgentState) -> dict:
    return await _run_stage_node(
        state,
        "signal_qualification",
        run_signal_qualification,
        capability_map=load_capability_map(),
    )


async def research_node(state: AgentState) -> dict:
    return await _run_stage_node(state, "research", run_research)


async def solution_mapping_node(state: AgentState) -> dict:
    return await _run_stage_node(
        state,
        "solution_mapping",
        run_solution_mapping,
        capability_map=load_capability_map(),
    )


async def persona_generation_node(state: AgentState) -> dict:
    """Run persona generation then apply HITL gate for companies needing selection."""
    result = await _run_stage_node(state, "persona_generation", run_persona_generation)

    # Apply HITL gate: mark companies without selected_personas as awaiting
    awaiting_ids = []
    for cid, cs in result.get("company_states", {}).items():
        if cs.get("status") not in _TERMINAL and not cs.get("selected_personas"):
            result["company_states"][cid] = run_persona_selection_gate(cs)
            awaiting_ids.append(cid)

    if awaiting_ids:
        result["awaiting_persona_selection"] = True
        result["awaiting_review"] = awaiting_ids

    return result


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------


def build_pipeline(checkpointer=None):
    """Assemble and compile the LangGraph StateGraph.

    Graph topology:
        orchestrator → signal_ingestion → signal_qualification → research
        → solution_mapping → persona_generation → hitl_gate → END

    Each stage is a separate node so graph.astream() emits a chunk at every
    stage boundary, enabling real-time WebSocket progress updates.

    Per-company parallelism is maintained within each node via asyncio.gather().

    The hitl_gate node detects companies awaiting persona selection and returns
    the awaiting flag so the caller can notify the UI. Resume happens outside
    LangGraph via the /sessions/.../personas/confirm endpoint, which drives
    run_synthesis + run_drafts_for_company directly.

    Args:
        checkpointer: LangGraph checkpointer. Optional; None is fine for the
                      normal run since HITL resume does not re-enter the graph.
    """
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("signal_ingestion", signal_ingestion_node)
    graph.add_node("signal_qualification", signal_qualification_node)
    graph.add_node("research", research_node)
    graph.add_node("solution_mapping", solution_mapping_node)
    graph.add_node("persona_generation", persona_generation_node)
    graph.add_node("hitl_gate", hitl_gate_node)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "signal_ingestion")
    graph.add_edge("signal_ingestion", "signal_qualification")
    graph.add_edge("signal_qualification", "research")
    graph.add_edge("research", "solution_mapping")
    graph.add_edge("solution_mapping", "persona_generation")
    graph.add_edge("persona_generation", "hitl_gate")
    graph.add_edge("hitl_gate", END)

    # langgraph dev may pass a dict or other config — normalize to a valid checkpointer
    if isinstance(checkpointer, dict) or (checkpointer is not None and not hasattr(checkpointer, 'aget')):
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        except ImportError:
            checkpointer = None

    return graph.compile(checkpointer=checkpointer)

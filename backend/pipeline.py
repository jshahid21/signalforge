"""LangGraph StateGraph assembly for SignalForge pipeline (no agent logic here).

Graph structure (Phase 5):
    orchestrator
        │  [conditional_edges → dispatch_companies → Send("company_pipeline")]
        ▼
    company_pipeline (runs per company in parallel)
        │
        ▼
      END

company_pipeline calls (per-company):
    signal_ingestion → signal_qualification → research → solution_mapping
    → persona_generation → [HITL gate: awaiting persona selection]
    → synthesis → drafts → done

The HITL gate is a logical pause — the pipeline returns AWAITING_HUMAN status.
Resume is triggered via the API (Phase 6) which calls apply_persona_selection()
and re-invokes the pipeline with selected_personas populated.

Nodes are imported from backend/agents/. This module only wires the graph.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agents.hitl_gate import (
    apply_persona_selection,
    hitl_gate_node,
    run_persona_selection_gate,
)
from backend.agents.orchestrator import dispatch_companies, orchestrator_node
from backend.agents.persona_generation import run_persona_generation
from backend.agents.research import run_research
from backend.agents.signal_ingestion import run_signal_ingestion
from backend.agents.signal_qualification import run_signal_qualification
from backend.agents.solution_mapping import run_solution_mapping
from backend.agents.synthesis import run_synthesis
from backend.agents.draft import run_drafts_for_company
from backend.agents.memory_agent import get_few_shot_examples
from backend.models.enums import PipelineStatus
from backend.models.state import AgentState, CompanyInput, CompanyState, SellerProfile
from backend.tools.jsearch import JSearchClient
from backend.tools.tavily import TavilySearchClient


async def company_pipeline(input: CompanyInput) -> dict:
    """Per-company processing node — receives CompanyInput via Send().

    Runs the full pipeline: ingestion → qualification → research → solution_mapping
    → persona_generation → synthesis → drafts.

    HITL gate: if selected_personas is empty after persona generation, the pipeline
    returns AWAITING_HUMAN. The API resumes by re-invoking with selected_personas set.

    Returns updates to AgentState (merged via reducers by LangGraph).
    """
    cs: CompanyState = input["company_state"]
    capability_map = input.get("capability_map")
    max_budget = input.get("max_budget_usd", 0.50)
    current_cost = input.get("total_cost_usd_at_dispatch", 0.0)
    jsearch_key = input.get("jsearch_api_key", "")
    tavily_key = input.get("tavily_api_key", "")
    llm_provider = input.get("llm_provider", "")
    llm_model = input.get("llm_model", "")
    seller_profile: SellerProfile = input.get("seller_profile", {})  # type: ignore[assignment]

    jsearch_client = JSearchClient(api_key=jsearch_key)
    tavily_client = TavilySearchClient(api_key=tavily_key)

    total_cost = 0.0
    company_id = cs["company_id"]

    def _failed(cs: CompanyState) -> dict:
        return {
            "company_states": {company_id: cs},
            "total_cost_usd": total_cost,
            "failed_company_ids": [company_id],
        }

    def _done(cs: CompanyState) -> dict:
        return {
            "company_states": {company_id: cs},
            "total_cost_usd": total_cost,
            "completed_company_ids": [company_id],
        }

    # Resume path: if selected_personas already populated, skip to synthesis
    already_has_selection = bool(cs.get("selected_personas"))
    skip_to_synthesis = (
        already_has_selection
        and cs.get("current_stage") in ("synthesis", "draft", "awaiting_persona_selection")
        and cs.get("qualified_signal") is not None
        and cs.get("solution_mapping") is not None
    )

    if not skip_to_synthesis:
        # === 1. Signal Ingestion ===
        cs, ingestion_cost = await run_signal_ingestion(
            cs=cs,
            capability_map=capability_map,
            current_total_cost=current_cost,
            max_budget_usd=max_budget,
            jsearch_client=jsearch_client,
            tavily_client=tavily_client,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        total_cost += ingestion_cost
        current_cost += ingestion_cost
        if cs["status"] == PipelineStatus.FAILED:
            return _failed(cs)

        # === 2. Signal Qualification ===
        cs, qual_cost = await run_signal_qualification(
            cs=cs,
            capability_map=capability_map,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_cost,
            max_budget_usd=max_budget,
        )
        total_cost += qual_cost
        current_cost += qual_cost
        if cs["status"] == PipelineStatus.SKIPPED:
            return _done(cs)
        if cs["status"] == PipelineStatus.FAILED:
            return _failed(cs)

        # === 3. Research ===
        cs, research_cost = await run_research(
            cs=cs,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_cost,
            max_budget_usd=max_budget,
        )
        total_cost += research_cost
        current_cost += research_cost
        if cs["status"] == PipelineStatus.FAILED:
            return _failed(cs)

        # === 4. Solution Mapping ===
        cs, mapping_cost = await run_solution_mapping(
            cs=cs,
            capability_map=capability_map,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_cost,
            max_budget_usd=max_budget,
        )
        total_cost += mapping_cost
        current_cost += mapping_cost
        if cs["status"] == PipelineStatus.FAILED:
            return _failed(cs)

        # === 5. Persona Generation ===
        cs, persona_cost = await run_persona_generation(
            cs=cs,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_cost,
            max_budget_usd=max_budget,
        )
        total_cost += persona_cost
        current_cost += persona_cost

        # === 6. HITL Gate — Persona Selection ===
        if not cs.get("selected_personas"):
            # No personas selected yet — pause for human input
            cs = run_persona_selection_gate(cs)
            return {
                "company_states": {company_id: cs},
                "total_cost_usd": total_cost,
                "awaiting_persona_selection": True,
                "awaiting_review": [company_id],
            }

    # === 7. Synthesis ===
    cs, synth_cost = await run_synthesis(
        cs=cs,
        llm_provider=llm_provider,
        llm_model=llm_model,
        current_total_cost=current_cost,
        max_budget_usd=max_budget,
    )
    total_cost += synth_cost
    current_cost += synth_cost
    if cs["status"] == PipelineStatus.FAILED:
        return _failed(cs)

    # === 8. Draft Generation ===
    few_shot = get_few_shot_examples(limit=2)
    cs, draft_cost = await run_drafts_for_company(
        cs=cs,
        seller_profile=seller_profile,
        llm_provider=llm_provider,
        llm_model=llm_model,
        current_total_cost=current_cost,
        max_budget_usd=max_budget,
        few_shot_examples=few_shot,
    )
    total_cost += draft_cost

    return _done(cs)


def build_pipeline(checkpointer=None):
    """Assemble and compile the LangGraph StateGraph.

    Graph topology:
        orchestrator → [dispatch_companies → Send("company_pipeline")] → hitl_gate → END

    The hitl_gate node:
    - Detects companies awaiting persona selection
    - Calls interrupt() to pause the graph for human input
    - On resume, applies selections and dispatches synthesis-only company_pipeline runs
    - Requires a checkpointer to support interrupt/resume

    Args:
        checkpointer: LangGraph checkpointer. Defaults to MemorySaver if None.
                     Pass AsyncSqliteSaver for persistent session storage.

    Usage with HITL:
        config = {"configurable": {"thread_id": "<unique-id>"}}
        # First invocation — may pause at hitl_gate
        result = await graph.ainvoke(initial_state, config=config)
        # Resume with persona selections: {company_id: [persona_id, ...]}
        result = await graph.ainvoke(
            Command(resume={"stripe": ["persona-id-1", "persona-id-2"]}),
            config=config,
        )
    """
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("company_pipeline", company_pipeline)
    graph.add_node("hitl_gate", hitl_gate_node)

    graph.add_conditional_edges(
        "orchestrator",
        dispatch_companies,
        ["company_pipeline"],
    )

    graph.add_edge("company_pipeline", "hitl_gate")
    graph.add_edge("hitl_gate", END)
    graph.set_entry_point("orchestrator")

    return graph.compile(checkpointer=checkpointer)

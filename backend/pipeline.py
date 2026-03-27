"""LangGraph StateGraph assembly for SignalForge pipeline (no agent logic here).

Graph structure (Phase 3):
    orchestrator
        │  [conditional_edges → dispatch_companies → Send("company_pipeline")]
        ▼
    company_pipeline (runs per company in parallel)
        │
        ▼
      END

company_pipeline calls:
    Phase 3: signal_ingestion → signal_qualification
    Phase 4+: + research → solution_mapping → persona_generation → ...

Nodes are imported from backend/agents/. This module only wires the graph.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agents.orchestrator import dispatch_companies, orchestrator_node
from backend.agents.signal_ingestion import run_signal_ingestion
from backend.agents.signal_qualification import run_signal_qualification
from backend.models.enums import PipelineStatus
from backend.models.state import AgentState, CompanyInput, CompanyState
from backend.tools.jsearch import JSearchClient
from backend.tools.tavily import TavilySearchClient


async def company_pipeline(input: CompanyInput) -> dict:
    """Per-company processing node — receives CompanyInput via Send().

    Runs signal_ingestion → signal_qualification in sequence for one company.
    Returns updates to AgentState (merged via reducers by LangGraph).

    Phase 4+ will extend this to also run research, solution_mapping,
    persona_generation, synthesis, and draft nodes.
    """
    cs: CompanyState = input["company_state"]
    capability_map = input.get("capability_map")
    max_budget = input.get("max_budget_usd", 0.50)
    current_cost = input.get("total_cost_usd_at_dispatch", 0.0)
    jsearch_key = input.get("jsearch_api_key", "")
    tavily_key = input.get("tavily_api_key", "")
    llm_provider = input.get("llm_provider", "")
    llm_model = input.get("llm_model", "")

    jsearch_client = JSearchClient(api_key=jsearch_key)
    tavily_client = TavilySearchClient(api_key=tavily_key)

    total_cost = 0.0
    company_id = cs["company_id"]

    # 1. Signal Ingestion
    cs, ingestion_cost = await run_signal_ingestion(
        cs=cs,
        capability_map=capability_map,
        current_total_cost=current_cost,
        max_budget_usd=max_budget,
        jsearch_client=jsearch_client,
        tavily_client=tavily_client,
    )
    total_cost += ingestion_cost
    current_cost += ingestion_cost

    # Budget exceeded or fatal error → stop this company
    if cs["status"] == PipelineStatus.FAILED:
        return {
            "company_states": {company_id: cs},
            "total_cost_usd": total_cost,
            "failed_company_ids": [company_id],
        }

    # 2. Signal Qualification
    cs, qual_cost = await run_signal_qualification(
        cs=cs,
        capability_map=capability_map,
        llm_provider=llm_provider,
        llm_model=llm_model,
        current_total_cost=current_cost,
        max_budget_usd=max_budget,
    )
    total_cost += qual_cost

    # Signal did not qualify → mark as skipped, no further processing
    if cs["status"] == PipelineStatus.SKIPPED:
        return {
            "company_states": {company_id: cs},
            "total_cost_usd": total_cost,
            "completed_company_ids": [company_id],
        }

    # Phase 4+ continues here (research, solution mapping, etc.)
    # For Phase 3, company is complete after qualification.
    return {
        "company_states": {company_id: cs},
        "total_cost_usd": total_cost,
        "completed_company_ids": [company_id],
    }


def build_pipeline():
    """Assemble and compile the LangGraph StateGraph.

    Returns a compiled graph ready to invoke with AgentState.
    """
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("company_pipeline", company_pipeline)

    # After orchestrator initializes company states, fan out to per-company pipelines
    graph.add_conditional_edges(
        "orchestrator",
        dispatch_companies,
        ["company_pipeline"],
    )

    # Each company_pipeline completes independently → END
    graph.add_edge("company_pipeline", END)

    # Entry point
    graph.set_entry_point("orchestrator")

    return graph.compile()

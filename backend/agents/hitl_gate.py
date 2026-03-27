"""HITL (Human-in-the-Loop) gate for persona selection (spec §5.7, §6.2).

This is a pipeline interrupt node — not an AI agent.
Pipeline pauses here until the user confirms persona selection via the API.

LangGraph interrupt() usage:
    - Node calls interrupt(value) to pause execution
    - Graph resumes when .invoke() called again with Command(resume=selected_personas)
    - Requires graph compiled with a MemorySaver checkpointer

State transitions:
    Before interrupt: awaiting_persona_selection = True
    After resume:     selected_personas populated, awaiting_persona_selection = False

HITL flow in graph:
    company_pipeline [fan-out] → hitl_gate → END
    company_pipeline returns AWAITING_HUMAN when personas need selection.
    hitl_gate detects these, calls interrupt(), and on resume dispatches
    synthesis-only company_pipeline runs via Command(send=[Send(...)]).
"""
from __future__ import annotations

from backend.models.enums import PipelineStatus
from backend.models.state import AgentState, CompanyInput, CompanyState


def run_persona_selection_gate(cs: CompanyState) -> CompanyState:
    """Mark the company as awaiting persona selection.

    Called before the LangGraph interrupt(). Sets the state flag that the UI
    uses to display the persona selection panel.

    Returns the updated company state.
    """
    cs = dict(cs)  # type: ignore[assignment]
    cs["status"] = PipelineStatus.AWAITING_HUMAN  # type: ignore[index]
    cs["current_stage"] = "awaiting_persona_selection"  # type: ignore[index]
    return cs  # type: ignore[return-value]


def apply_persona_selection(
    cs: CompanyState,
    selected_persona_ids: list[str],
) -> CompanyState:
    """Apply user's persona selection to the company state.

    Called when the user confirms their selection. Validates that all provided
    persona IDs exist in the generated set; skips unknown IDs.

    Returns updated company state ready for synthesis.
    """
    generated_ids = {p["persona_id"] for p in cs.get("generated_personas", [])}
    valid_selections = [pid for pid in selected_persona_ids if pid in generated_ids]

    cs = dict(cs)  # type: ignore[assignment]
    cs["selected_personas"] = valid_selections  # type: ignore[index]
    cs["current_stage"] = "synthesis"  # type: ignore[index]
    cs["status"] = PipelineStatus.RUNNING  # type: ignore[index]
    return cs  # type: ignore[return-value]


async def hitl_gate_node(state: AgentState) -> dict:
    """LangGraph node — pauses the graph for human persona selection.

    Sits between company_pipeline fan-out results and END. Detects companies
    with current_stage == "awaiting_persona_selection", calls interrupt() to
    pause the graph, and on resume dispatches synthesis-only company_pipeline
    runs via Command(send=[Send(...)]).

    Requires the graph to be compiled with a MemorySaver checkpointer.

    Resume value format: {company_id: [persona_id, ...], ...}
    """
    from backend.config.capability_map import load_capability_map
    from backend.config.loader import load_config

    try:
        from langgraph.types import Command, Send
        from langgraph.types import interrupt as langgraph_interrupt
    except ImportError:
        # LangGraph interrupt not available — return no-op
        return {"awaiting_persona_selection": False}

    company_states = state.get("company_states", {})
    awaiting = {
        company_id: cs
        for company_id, cs in company_states.items()
        if cs.get("current_stage") == "awaiting_persona_selection"
    }

    if not awaiting:
        return {"awaiting_persona_selection": False}

    # Pause and surface generated personas to the UI/API
    selections: dict[str, list[str]] = langgraph_interrupt({
        "awaiting_persona_selection": {
            company_id: cs.get("generated_personas", [])
            for company_id, cs in awaiting.items()
        }
    })
    # selections = {company_id: [persona_id, ...]} — provided by Command(resume=...)

    # Apply selections and dispatch synthesis runs.
    # Only dispatch companies that received non-empty persona selections.
    # Companies omitted from the resume payload (empty selection list) remain in
    # AWAITING_HUMAN and are NOT re-dispatched, preventing a full pipeline re-run.
    config = load_config()
    capability_map = load_capability_map()

    updated_states: dict = {}
    sends: list = []
    for company_id, cs in awaiting.items():
        selected_ids = selections.get(company_id, []) if isinstance(selections, dict) else []
        if not selected_ids:
            # No selection provided — leave this company in AWAITING_HUMAN.
            # The caller must include persona_ids for each company in the resume payload.
            updated_states[company_id] = cs
            continue
        updated_cs = apply_persona_selection(cs, selected_ids)
        updated_states[company_id] = updated_cs
        sends.append(Send("company_pipeline", CompanyInput(
            company_state=updated_cs,
            seller_profile=state.get("seller_profile", {}),  # type: ignore[arg-type]
            max_budget_usd=config.session_budget.max_usd,
            total_cost_usd_at_dispatch=state.get("total_cost_usd", 0.0),
            capability_map=capability_map,
            jsearch_api_key=config.api_keys.jsearch,
            tavily_api_key=config.api_keys.tavily,
            llm_provider=config.api_keys.llm_provider,
            llm_model=config.api_keys.llm_model,
        )))

    return Command(  # type: ignore[return-value]
        update={
            "company_states": updated_states,
            "awaiting_persona_selection": False,
            "awaiting_review": [],
        },
        goto=sends,
    )

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
"""
from __future__ import annotations

from typing import Any

from backend.models.state import CompanyState


def run_persona_selection_gate(cs: CompanyState) -> CompanyState:
    """Mark the company as awaiting persona selection.

    Called before the LangGraph interrupt(). Sets the state flag that the UI
    uses to display the persona selection panel.

    Returns the updated company state.
    """
    cs = dict(cs)  # type: ignore[assignment]
    # Clear any previously selected personas to require fresh selection
    cs["status"] = "awaiting_human"  # type: ignore[index]
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
    cs["status"] = "running"  # type: ignore[index]
    return cs  # type: ignore[return-value]


async def hitl_persona_selection_node(state: Any) -> dict:
    """LangGraph node — pauses the graph for human persona selection.

    This node is called by LangGraph after persona generation. It uses
    LangGraph's interrupt() to pause execution until the API provides
    selected_personas via Command(resume=...).

    The interrupt value is the list of generated personas for the UI to display.
    """
    try:
        from langgraph.types import interrupt as langgraph_interrupt
    except ImportError:
        # Fallback: if LangGraph interrupt not available, return state unchanged
        return {}

    company_states = state.get("company_states", {})
    # Collect all companies awaiting selection
    pending: dict[str, list] = {}
    for company_id, cs in company_states.items():
        if cs.get("current_stage") == "awaiting_persona_selection":
            pending[company_id] = cs.get("generated_personas", [])

    if pending:
        # Interrupt and wait for human input
        langgraph_interrupt({"awaiting_persona_selection": pending})

    return {"awaiting_persona_selection": False}

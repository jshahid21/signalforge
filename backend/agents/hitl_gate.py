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
    """LangGraph node — signals that human persona selection is required.

    Detects companies with current_stage == "awaiting_persona_selection" and
    returns the HITL flag so the application layer can pause and notify the UI.
    Resume is handled outside LangGraph (personas confirm endpoint calls
    synthesis/draft directly) to avoid LangGraph checkpoint serialization issues
    with Send objects.
    """
    company_states = state.get("company_states", {})
    awaiting_ids = [
        company_id
        for company_id, cs in company_states.items()
        if cs.get("current_stage") == "awaiting_persona_selection"
    ]

    if not awaiting_ids:
        return {"awaiting_persona_selection": False}

    return {
        "awaiting_persona_selection": True,
        "awaiting_review": awaiting_ids,
    }

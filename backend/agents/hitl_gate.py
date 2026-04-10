"""HITL (Human-in-the-Loop) gate for persona selection (spec §5.7, §6.2).

This is a pipeline signalling node — not an AI agent. When companies require
persona selection, the graph exits through this node and the application layer
(the `/sessions/.../personas/confirm` endpoint) drives synthesis/draft outside
LangGraph. The graph itself does NOT call `interrupt()` anymore — LangGraph's
checkpointer could not serialize the Send objects dispatched on resume, so the
HITL pause was moved out of the graph entirely.

Flow:
    company_pipeline [fan-out] → hitl_gate → END
    company_pipeline sets current_stage="awaiting_persona_selection" for each
    company that needs a persona pick.
    hitl_gate_node collects those company IDs and returns the
    awaiting_persona_selection flag so the caller can broadcast the HITL
    required event over WebSocket and return control to the user.

    The `/personas/confirm` endpoint later calls `apply_persona_selection`
    on each company state and invokes `run_synthesis` + `run_drafts_for_company`
    directly — no graph resume is involved.
"""
from __future__ import annotations

from backend.models.enums import PipelineStatus
from backend.models.state import AgentState, CompanyInput, CompanyState


def run_persona_selection_gate(cs: CompanyState) -> CompanyState:
    """Mark the company as awaiting persona selection.

    Called from `company_pipeline` when personas have been generated and need
    human confirmation. Sets the state flag that the UI uses to display the
    persona selection panel. The graph then exits via `hitl_gate_node`; resume
    is performed out of graph by the `/personas/confirm` endpoint.

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

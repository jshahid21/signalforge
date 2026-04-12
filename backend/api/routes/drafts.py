"""Draft routes — regenerate and approve drafts."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.session_store import (
    get_active_session,
    get_session_record,
    load_and_register_session,
    save_session_state,
)

router = APIRouter(
    prefix="/sessions/{session_id}/companies/{company_id}/drafts",
    tags=["drafts"],
)


class RegenerateDraftRequest(BaseModel):
    override_requested: bool = False
    override_reason: Optional[str] = None


@router.post("/{persona_id}/regenerate", status_code=202)
async def regenerate_draft(
    session_id: str,
    company_id: str,
    persona_id: str,
    body: RegenerateDraftRequest,
) -> dict:
    """Regenerate a draft for a specific (company, persona) pair.

    Increments Draft.version. Runs Draft Agent synchronously and updates
    the in-memory session state.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        active = load_and_register_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Session not active")

    cs = active.last_state.get("company_states", {}).get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    personas = {p["persona_id"]: p for p in cs.get("generated_personas", [])}
    persona = personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    from backend.agents.draft import run_draft
    from backend.config.loader import load_config
    from backend.models.state import SellerProfile

    config_obj = load_config()
    seller_profile = SellerProfile(
        company_name=config_obj.seller_profile.company_name,
        portfolio_summary=config_obj.seller_profile.portfolio_summary,
        portfolio_items=config_obj.seller_profile.portfolio_items,
    )

    # Apply override if requested
    cs_for_draft = dict(cs)
    if body.override_requested:
        cs_for_draft["override_requested"] = True
        cs_for_draft["override_reason"] = body.override_reason

    existing_draft = cs.get("drafts", {}).get(persona_id)

    draft, cost = await run_draft(
        cs=cs_for_draft,  # type: ignore[arg-type]
        persona=persona,  # type: ignore[arg-type]
        seller_profile=seller_profile,
        llm_provider=config_obj.api_keys.llm_provider,
        llm_model=config_obj.api_keys.llm_model,
        current_total_cost=active.last_state.get("total_cost_usd", 0.0),
        max_budget_usd=config_obj.session_budget.max_usd,
        existing_draft=existing_draft,  # type: ignore[arg-type]
    )

    if draft is not None:
        # Log rejection feedback for the previous draft (regeneration = rejection)
        old_draft = cs.get("drafts", {}).get(persona_id)
        if old_draft and old_draft.get("run_id"):
            from backend.utils.langsmith_feedback import log_draft_feedback
            log_draft_feedback(
                run_id=old_draft["run_id"],
                approved=False,
                comment=body.override_reason,
            )

        # Update in-memory state
        drafts = dict(cs.get("drafts", {}))
        drafts[persona_id] = draft
        cs = dict(cs)
        cs["drafts"] = drafts
        company_states = dict(active.last_state.get("company_states", {}))
        company_states[company_id] = cs
        active.last_state = dict(active.last_state)
        active.last_state["company_states"] = company_states
        # Accumulate cost
        active.last_state["total_cost_usd"] = active.last_state.get("total_cost_usd", 0.0) + cost
        save_session_state(session_id, active.last_state)

        return {"message": "Draft regenerated", "draft": dict(draft)}

    raise HTTPException(
        status_code=422,
        detail="Draft could not be generated (confidence gate or budget exceeded).",
    )


@router.post("/{persona_id}/approve", status_code=200)
async def approve_draft(
    session_id: str,
    company_id: str,
    persona_id: str,
) -> dict:
    """Approve a draft — marks it approved and writes to the Memory store.

    Triggers Memory Agent to persist the (company, persona, draft) record
    for future few-shot injection.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        active = load_and_register_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Session not active")

    cs = active.last_state.get("company_states", {}).get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    draft = cs.get("drafts", {}).get(persona_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found for this persona")

    personas = {p["persona_id"]: p for p in cs.get("generated_personas", [])}
    persona = personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Log approval feedback to LangSmith
    if draft.get("run_id"):
        from backend.utils.langsmith_feedback import log_draft_feedback
        log_draft_feedback(run_id=draft["run_id"], approved=True)

    # Mark draft as approved in memory
    draft = dict(draft)
    draft["approved"] = True

    # Update in-memory state
    drafts = dict(cs.get("drafts", {}))
    drafts[persona_id] = draft
    cs = dict(cs)
    cs["drafts"] = drafts
    company_states = dict(active.last_state.get("company_states", {}))
    company_states[company_id] = cs
    active.last_state = dict(active.last_state)
    active.last_state["company_states"] = company_states
    save_session_state(session_id, active.last_state)

    # Write to Memory Agent
    from backend.agents.memory_agent import write_memory_record
    from backend.models.state import Draft, Persona, QualifiedSignal, SynthesisOutput

    qualified_signal = cs.get("qualified_signal")
    synthesis_output = cs.get("synthesis_outputs", {}).get(persona_id)

    record = write_memory_record(
        company_name=cs.get("company_name", company_id),
        persona=persona,  # type: ignore[arg-type]
        draft=draft,  # type: ignore[arg-type]
        qualified_signal=qualified_signal,  # type: ignore[arg-type]
        synthesis=synthesis_output,  # type: ignore[arg-type]
    )

    return {
        "message": "Draft approved and saved to memory",
        "record_id": record.record_id,
        "draft": draft,
    }

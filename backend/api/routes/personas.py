"""Persona routes — persona selection (HITL) and persona editing."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.session_store import get_active_session, get_async_checkpointer, get_session_record, update_session_record
from backend.api.websocket import manager

router = APIRouter(prefix="/sessions/{session_id}/companies/{company_id}/personas", tags=["personas"])


class ConfirmPersonasRequest(BaseModel):
    selected_persona_ids: list[str]
    custom_personas: list[dict] = []    # Optional custom personas added by user


class EditPersonaRequest(BaseModel):
    title: Optional[str] = None
    targeting_reason: Optional[str] = None


@router.post("/confirm", status_code=202)
async def confirm_persona_selection(
    session_id: str,
    company_id: str,
    body: ConfirmPersonasRequest,
) -> dict:
    """Confirm persona selection for HITL gate — resumes the pipeline.

    Passes selected_persona_ids to the paused LangGraph graph via
    Command(resume={company_id: selected_ids}).

    The pipeline resumes at the hitl_gate_node, applies selections,
    and dispatches synthesis runs.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None:
        raise HTTPException(status_code=404, detail="Session not active")

    if not active.awaiting_persona_selection:
        raise HTTPException(
            status_code=409,
            detail="Session is not awaiting persona selection",
        )

    # Build resume payload: {company_id: [selected_persona_ids]}
    resume_payload = {company_id: body.selected_persona_ids}

    # Pre-compute updated company states with custom personas for in-memory state
    updated_company_states: Optional[dict] = None
    if body.custom_personas and active.last_state:
        company_states = dict(active.last_state.get("company_states", {}))
        if company_id in company_states:
            cs = dict(company_states[company_id])
            existing = list(cs.get("generated_personas", []))
            existing.extend(body.custom_personas)
            cs["generated_personas"] = existing
            company_states[company_id] = cs
            updated_company_states = company_states
            active.last_state = dict(active.last_state)
            active.last_state["company_states"] = company_states

    import asyncio
    from langgraph.types import Command

    config = {"configurable": {"thread_id": session_id}}

    active.awaiting_persona_selection = False
    update_session_record(session_id, "running")

    async def _resume() -> None:
        """Resume LangGraph pipeline after HITL persona selection.

        Opens a fresh checkpointer, persists any custom personas to the
        checkpoint via aupdate_state(), then invokes Command(resume=...).
        """
        from backend.pipeline import build_pipeline

        try:
            async with get_async_checkpointer() as checkpointer:
                graph = build_pipeline(checkpointer=checkpointer)

                # Persist custom personas to the checkpoint before resuming
                if updated_company_states is not None:
                    await graph.aupdate_state(
                        config,
                        {"company_states": updated_company_states},
                    )

                result = await graph.ainvoke(
                    Command(resume=resume_payload),
                    config=config,
                )

            active.last_state = result

            # Check if more companies need HITL selection
            still_awaiting = {}
            for cid, cs in result.get("company_states", {}).items():
                if cs.get("current_stage") == "awaiting_persona_selection":
                    still_awaiting[cid] = cs.get("generated_personas", [])

            if still_awaiting:
                active.awaiting_persona_selection = True
                update_session_record(session_id, "awaiting_human")
                await manager.broadcast_hitl_required(session_id, still_awaiting)
            else:
                update_session_record(session_id, "completed")
                await manager.broadcast_pipeline_complete(session_id)
        except Exception as exc:
            update_session_record(session_id, "failed", error_message=str(exc))
            await manager.broadcast_error(session_id, str(exc))

    task = asyncio.create_task(_resume())
    active.task = task

    return {
        "message": "Persona selection confirmed. Pipeline resuming.",
        "session_id": session_id,
        "company_id": company_id,
        "selected_persona_ids": body.selected_persona_ids,
    }


@router.put("/{persona_id}", status_code=200)
async def edit_persona(
    session_id: str,
    company_id: str,
    persona_id: str,
    body: EditPersonaRequest,
) -> dict:
    """Edit a persona's title or targeting_reason.

    Marks the persona as is_edited=True. Does not re-trigger pipeline agents.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Session not active")

    company_states = active.last_state.get("company_states", {})
    cs = company_states.get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    personas = cs.get("generated_personas", [])
    persona = next((p for p in personas if p["persona_id"] == persona_id), None)
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Apply edits
    persona = dict(persona)
    if body.title is not None:
        persona["title"] = body.title
    if body.targeting_reason is not None:
        persona["targeting_reason"] = body.targeting_reason
    persona["is_edited"] = True

    # Update in-memory state
    updated_personas = [
        persona if p["persona_id"] == persona_id else p
        for p in personas
    ]
    cs = dict(cs)
    cs["generated_personas"] = updated_personas
    company_states = dict(company_states)
    company_states[company_id] = cs
    active.last_state = dict(active.last_state)
    active.last_state["company_states"] = company_states

    return {"message": "Persona updated", "persona": persona}

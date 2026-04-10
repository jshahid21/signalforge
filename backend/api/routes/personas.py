"""Persona routes — persona selection (HITL) and persona editing."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.session_store import (
    get_active_session,
    get_session_record,
    load_and_register_session,
    save_session_state,
    update_session_record,
)
from backend.api.websocket import manager

logger = logging.getLogger(__name__)

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
    """Confirm persona selection for HITL gate — runs synthesis/draft directly.

    Applies selected personas to the company state and dispatches synthesis
    and draft generation without re-entering LangGraph (avoids Send serialization
    issues with LangGraph checkpointers).
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        active = load_and_register_session(session_id)
    if active is None:
        raise HTTPException(status_code=404, detail="Session not active")

    if not active.awaiting_persona_selection:
        raise HTTPException(
            status_code=409,
            detail="Session is not awaiting persona selection",
        )

    if active.last_state is None:
        raise HTTPException(status_code=409, detail="No pipeline state available")

    # Apply custom personas to generated list
    company_states = dict(active.last_state.get("company_states", {}))
    if company_id not in company_states:
        raise HTTPException(status_code=404, detail="Company not found in session")

    cs = dict(company_states[company_id])
    if body.custom_personas:
        existing = list(cs.get("generated_personas", []))
        existing.extend(body.custom_personas)
        cs["generated_personas"] = existing

    # Apply persona selection
    from backend.agents.hitl_gate import apply_persona_selection
    cs = apply_persona_selection(cs, body.selected_persona_ids)
    company_states[company_id] = cs
    active.last_state = dict(active.last_state)
    active.last_state["company_states"] = company_states

    # Check if all awaiting companies now have selections
    still_awaiting = [
        cid for cid, cstate in company_states.items()
        if cstate.get("current_stage") == "awaiting_persona_selection"
    ]

    active.awaiting_persona_selection = bool(still_awaiting)

    if still_awaiting:
        update_session_record(session_id, "awaiting_human")
        return {
            "message": "Persona selection saved. Waiting for remaining companies.",
            "session_id": session_id,
            "company_id": company_id,
            "still_awaiting": still_awaiting,
        }

    # All companies confirmed — run synthesis/draft for all selected companies
    update_session_record(session_id, "running")

    async def _run_synthesis_phase() -> None:
        from backend.agents.synthesis import run_synthesis
        from backend.agents.draft import run_drafts_for_company
        from backend.agents.memory_agent import get_few_shot_examples
        from backend.config.loader import load_config
        from backend.models.state import SellerProfile

        try:
            config = load_config()
            llm_provider = config.api_keys.llm_provider
            llm_model = config.api_keys.llm_model
            max_budget = config.session_budget.max_usd
            current_cost = active.last_state.get("total_cost_usd", 0.0)  # type: ignore[union-attr]
            seller_profile = SellerProfile(
                company_name=config.seller_profile.company_name,
                portfolio_summary=config.seller_profile.portfolio_summary,
                portfolio_items=config.seller_profile.portfolio_items,
            )

            states = dict(active.last_state.get("company_states", {}))  # type: ignore[union-attr]
            total_cost = 0.0

            from backend.models.enums import PipelineStatus
            for cid, cstate in states.items():
                if cstate.get("current_stage") != "synthesis":
                    continue

                await manager.broadcast_stage_update(session_id, cid, "synthesis", "running", company_state=cstate)

                cstate, synth_cost = await run_synthesis(
                    cs=cstate,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    current_total_cost=current_cost + total_cost,
                    max_budget_usd=max_budget,
                )
                total_cost += synth_cost

                if cstate.get("status") in (PipelineStatus.FAILED, "failed"):
                    states[cid] = cstate
                    await manager.broadcast_stage_update(session_id, cid, "synthesis", "failed")
                    continue

                await manager.broadcast_stage_update(session_id, cid, "draft", "running", company_state=cstate)

                few_shot = get_few_shot_examples(limit=2)
                cstate, draft_cost = await run_drafts_for_company(
                    cs=cstate,
                    seller_profile=seller_profile,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    current_total_cost=current_cost + total_cost,
                    max_budget_usd=max_budget,
                    few_shot_examples=few_shot,
                )
                total_cost += draft_cost
                states[cid] = cstate

                status_str = "completed" if cstate.get("status") not in (PipelineStatus.FAILED, "failed") else "failed"
                await manager.broadcast_stage_update(session_id, cid, "draft", status_str, company_state=cstate)

            # Update session state
            active.last_state = dict(active.last_state)  # type: ignore[union-attr]
            active.last_state["company_states"] = states
            active.last_state["total_cost_usd"] = current_cost + total_cost

            save_session_state(session_id, active.last_state)  # type: ignore[arg-type]
            update_session_record(session_id, "completed")
            await manager.broadcast_pipeline_complete(session_id)

        except Exception as exc:
            import traceback
            logger.error("Synthesis phase failed for session %s: %s\n%s",
                         session_id, exc, traceback.format_exc())
            update_session_record(session_id, "failed", error_message=str(exc))
            await manager.broadcast_error(session_id, str(exc))

    task = asyncio.create_task(_run_synthesis_phase())
    active.task = task

    return {
        "message": "Persona selection confirmed. Synthesis starting.",
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
    """Edit a persona's title or targeting_reason."""
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        active = load_and_register_session(session_id)
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

    persona = dict(persona)
    if body.title is not None:
        persona["title"] = body.title
    if body.targeting_reason is not None:
        persona["targeting_reason"] = body.targeting_reason
    persona["is_edited"] = True

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

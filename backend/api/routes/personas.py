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

            # Track per-company outcome for final session status propagation
            # (issue #8 bug 4). Only companies that were actually dispatched
            # into synthesis are considered.
            processed_ids: list[str] = []
            failed_ids: list[str] = []

            def _is_failed(state: dict) -> bool:
                return state.get("status") in (PipelineStatus.FAILED, "failed")

            for cid, cstate in states.items():
                if cstate.get("current_stage") != "synthesis":
                    continue

                processed_ids.append(cid)
                await manager.broadcast_stage_update(session_id, cid, "synthesis", "running", company_state=cstate)

                try:
                    cstate, synth_cost = await run_synthesis(
                        cs=cstate,
                        llm_provider=llm_provider,
                        llm_model=llm_model,
                        current_total_cost=current_cost + total_cost,
                        max_budget_usd=max_budget,
                    )
                except Exception as synth_exc:
                    logger.error(
                        "Synthesis crashed for session %s company %s: %s",
                        session_id, cid, synth_exc,
                    )
                    cstate = dict(cstate)
                    cstate["status"] = PipelineStatus.FAILED
                    cstate["error_message"] = f"synthesis: {synth_exc}"
                    states[cid] = cstate
                    failed_ids.append(cid)
                    await manager.broadcast_stage_update(session_id, cid, "synthesis", "failed")
                    continue

                total_cost += synth_cost

                if _is_failed(cstate):
                    states[cid] = cstate
                    failed_ids.append(cid)
                    await manager.broadcast_stage_update(session_id, cid, "synthesis", "failed")
                    continue

                await manager.broadcast_stage_update(session_id, cid, "draft", "running", company_state=cstate)

                few_shot = get_few_shot_examples(limit=2)
                try:
                    cstate, draft_cost = await run_drafts_for_company(
                        cs=cstate,
                        seller_profile=seller_profile,
                        llm_provider=llm_provider,
                        llm_model=llm_model,
                        current_total_cost=current_cost + total_cost,
                        max_budget_usd=max_budget,
                        few_shot_examples=few_shot,
                    )
                except Exception as draft_exc:
                    logger.error(
                        "Draft crashed for session %s company %s: %s",
                        session_id, cid, draft_exc,
                    )
                    cstate = dict(cstate)
                    cstate["status"] = PipelineStatus.FAILED
                    cstate["error_message"] = f"draft: {draft_exc}"
                    states[cid] = cstate
                    failed_ids.append(cid)
                    await manager.broadcast_stage_update(session_id, cid, "draft", "failed")
                    continue

                total_cost += draft_cost
                states[cid] = cstate

                if _is_failed(cstate):
                    failed_ids.append(cid)
                    status_str = "failed"
                else:
                    status_str = "completed"
                await manager.broadcast_stage_update(session_id, cid, "draft", status_str, company_state=cstate)

            # Update session state
            active.last_state = dict(active.last_state)  # type: ignore[union-attr]
            active.last_state["company_states"] = states
            active.last_state["total_cost_usd"] = current_cost + total_cost

            save_session_state(session_id, active.last_state)  # type: ignore[arg-type]

            # Derive session status from per-company outcomes (issue #8 bug 4):
            #   all succeeded → completed
            #   all failed    → failed
            #   mixed         → partial
            if not processed_ids:
                final_status = PipelineStatus.COMPLETED.value
                err_msg = None
            elif not failed_ids:
                final_status = PipelineStatus.COMPLETED.value
                err_msg = None
            elif len(failed_ids) == len(processed_ids):
                final_status = PipelineStatus.FAILED.value
                err_msg = f"All companies failed: {', '.join(failed_ids)}"
            else:
                final_status = PipelineStatus.PARTIAL.value
                err_msg = f"{len(failed_ids)}/{len(processed_ids)} companies failed: {', '.join(failed_ids)}"

            update_session_record(session_id, final_status, error_message=err_msg)

            # Broadcast pipeline_complete on ANY terminal state so the UI can
            # finalize (stop spinners, enable actions). Failure details go out
            # separately via broadcast_error so the UI can surface them without
            # leaving the pipeline stuck in a non-terminal state.
            if err_msg:
                await manager.broadcast_error(session_id, err_msg)
            await manager.broadcast_pipeline_complete(session_id)

        except Exception as exc:
            import traceback
            from backend.models.enums import PipelineStatus as _PipelineStatus
            logger.error("Synthesis phase failed for session %s: %s\n%s",
                         session_id, exc, traceback.format_exc())
            update_session_record(
                session_id, _PipelineStatus.FAILED.value, error_message=str(exc)
            )
            # Broadcast pipeline_complete on terminal state so the UI can
            # finalize (stop spinners, enable actions). broadcast_error
            # carries the failure detail.
            await manager.broadcast_error(session_id, str(exc))
            await manager.broadcast_pipeline_complete(session_id)

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

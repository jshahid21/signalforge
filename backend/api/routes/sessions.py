"""Session routes — POST /sessions, GET /sessions, GET /sessions/{id}, POST /sessions/{id}/resume."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.session_store import (
    ActiveSession,
    create_session_record,
    generate_session_id,
    get_active_session,
    get_async_checkpointer,
    get_session_record,
    list_session_records,
    register_session,
    update_session_record,
)
from backend.api.websocket import manager
from backend.config.loader import load_config
from backend.models.enums import PipelineStatus
from backend.models.state import AgentState, SellerProfile

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    company_names: list[str]
    seller_profile: Optional[dict] = None  # overrides config if provided


class SessionResponse(BaseModel):
    session_id: str
    status: str
    company_names: list[str]
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


def _status_value(status: Any) -> str:
    """Serialize a PipelineStatus enum or string to its plain string value."""
    if isinstance(status, PipelineStatus):
        return status.value
    return str(status)


async def _run_pipeline_task(
    session_id: str,
    initial_state: AgentState,
) -> None:
    """Background task: run the pipeline with real-time WebSocket events.

    Uses graph.astream() to emit stage_update events at each agent completion.
    The checkpointer is opened and closed within this task; if the pipeline
    pauses at the HITL gate, the checkpoint is saved to disk and a new
    checkpointer connection is opened by the resume endpoint.
    """
    from backend.pipeline import build_pipeline

    active = get_active_session(session_id)
    if active is None:
        return

    config = {"configurable": {"thread_id": session_id}}

    try:
        config_obj = load_config()
        max_budget = config_obj.session_budget.max_usd

        await manager.broadcast(session_id, {
            "type": "pipeline_started",
            "session_id": session_id,
        })

        async with get_async_checkpointer() as checkpointer:
            graph = build_pipeline(checkpointer=checkpointer)

            # Stream events from graph — emit WebSocket events per stage
            final_state: dict = {}
            async for chunk in graph.astream(initial_state, config=config):
                for node_name, node_output in chunk.items():
                    if not isinstance(node_output, dict):
                        continue
                    # Emit stage updates for each company that changed in this chunk
                    company_states = node_output.get("company_states", {})
                    for company_id, cs in company_states.items():
                        if not isinstance(cs, dict):
                            continue
                        stage = cs.get("current_stage", "")
                        status = _status_value(cs.get("status", "running"))
                        await manager.broadcast_stage_update(
                            session_id, company_id, stage, status
                        )
                    final_state.update(node_output)

        active.last_state = final_state

        # Check for HITL pause
        awaiting = {}
        for company_id, cs in final_state.get("company_states", {}).items():
            if isinstance(cs, dict) and cs.get("current_stage") == "awaiting_persona_selection":
                awaiting[company_id] = cs.get("generated_personas", [])

        if awaiting:
            active.awaiting_persona_selection = True
            update_session_record(session_id, "awaiting_human")
            await manager.broadcast_hitl_required(session_id, awaiting)
        else:
            update_session_record(session_id, "completed")
            await manager.broadcast_pipeline_complete(session_id)

        # Budget warning: if total cost >= 80% of max
        total_cost = final_state.get("total_cost_usd", 0.0)
        if max_budget > 0 and (total_cost / max_budget) >= 0.8:
            await manager.broadcast_budget_warning(
                session_id,
                pct_used=round((total_cost / max_budget) * 100, 1),
            )

    except Exception as exc:
        err_msg = str(exc)
        update_session_record(session_id, "failed", error_message=err_msg)
        await manager.broadcast_error(session_id, err_msg)


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: StartSessionRequest,
) -> SessionResponse:
    """Start a new pipeline session.

    Creates a session record and starts the pipeline as a background task.
    Returns session_id immediately; use GET /sessions/{id} to poll status
    or connect to ws://<host>/ws/<session_id> for real-time events.
    """
    config = load_config()

    # Resolve seller profile
    seller_profile_raw = body.seller_profile or {
        "company_name": config.seller_profile.company_name,
        "portfolio_summary": config.seller_profile.portfolio_summary,
        "portfolio_items": config.seller_profile.portfolio_items,
    }
    seller_profile = SellerProfile(
        company_name=seller_profile_raw.get("company_name", ""),
        portfolio_summary=seller_profile_raw.get("portfolio_summary", ""),
        portfolio_items=seller_profile_raw.get("portfolio_items", []),
    )

    session_id = generate_session_id()

    # Build initial AgentState
    initial_state = AgentState(
        target_companies=body.company_names,
        seller_profile=seller_profile,
        company_states={},
        pipeline_started_at="",
        pipeline_completed_at=None,
        active_company_ids=[],
        completed_company_ids=[],
        failed_company_ids=[],
        awaiting_persona_selection=False,
        awaiting_review=[],
        execution_log=[],
        total_cost_usd=0.0,
        final_drafts=[],
    )

    # Persist metadata
    create_session_record(
        session_id=session_id,
        company_names=body.company_names,
        seller_profile=seller_profile_raw,
    )

    active = ActiveSession(session_id=session_id)
    register_session(active)

    # Start pipeline in background — checkpointer is managed inside the task
    task = asyncio.create_task(
        _run_pipeline_task(session_id, initial_state)
    )
    active.task = task

    rec = get_session_record(session_id)
    return SessionResponse(
        session_id=session_id,
        status="running",
        company_names=body.company_names,
        created_at=rec["created_at"] if rec else None,
    )


@router.post("/{session_id}/resume", status_code=202)
async def resume_session(session_id: str) -> dict:
    """Resume a session from its SqliteSaver checkpoint (after process restart).

    The LangGraph SqliteSaver persists graph state to disk. On process restart,
    this endpoint rehydrates the session by:
    1. Loading session metadata from SQLite
    2. Creating a new pipeline graph connected to the existing checkpoint DB
    3. Calling graph.ainvoke(None, ...) to resume from the last checkpoint

    This endpoint is for process-restart recovery. For HITL persona selection,
    use POST /sessions/{id}/companies/{cid}/personas/confirm instead.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if rec["status"] not in ("running", "awaiting_human", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Session cannot be resumed (status: {rec['status']})",
        )

    # Check if session is already active in memory
    existing_active = get_active_session(session_id)
    if existing_active and existing_active.task and not existing_active.task.done():
        raise HTTPException(status_code=409, detail="Session is already running")

    active = ActiveSession(session_id=session_id)
    register_session(active)

    async def _resume_task() -> None:
        """Resume pipeline from checkpointed state — checkpointer managed inside task."""
        from backend.pipeline import build_pipeline

        config = {"configurable": {"thread_id": session_id}}
        try:
            update_session_record(session_id, "running")
            await manager.broadcast(session_id, {
                "type": "pipeline_resumed",
                "session_id": session_id,
            })

            async with get_async_checkpointer() as checkpointer:
                graph = build_pipeline(checkpointer=checkpointer)

                # Pass None to resume from checkpointed state
                final_state: dict = {}
                async for chunk in graph.astream(None, config=config):  # type: ignore[arg-type]
                    for node_name, node_output in chunk.items():
                        if not isinstance(node_output, dict):
                            continue
                        for company_id, cs in node_output.get("company_states", {}).items():
                            if not isinstance(cs, dict):
                                continue
                            stage = cs.get("current_stage", "")
                            status = _status_value(cs.get("status", "running"))
                            await manager.broadcast_stage_update(
                                session_id, company_id, stage, status
                            )
                        final_state.update(node_output)

            active.last_state = final_state

            awaiting = {}
            for company_id, cs in final_state.get("company_states", {}).items():
                if isinstance(cs, dict) and cs.get("current_stage") == "awaiting_persona_selection":
                    awaiting[company_id] = cs.get("generated_personas", [])

            if awaiting:
                active.awaiting_persona_selection = True
                update_session_record(session_id, "awaiting_human")
                await manager.broadcast_hitl_required(session_id, awaiting)
            else:
                update_session_record(session_id, "completed")
                await manager.broadcast_pipeline_complete(session_id)
        except Exception as exc:
            err_msg = str(exc)
            update_session_record(session_id, "failed", error_message=err_msg)
            await manager.broadcast_error(session_id, err_msg)

    task = asyncio.create_task(_resume_task())
    active.task = task

    return {
        "message": "Session resuming from checkpoint",
        "session_id": session_id,
    }


@router.get("", response_model=list[dict])
async def list_sessions() -> list[dict]:
    """List all sessions (most recent first)."""
    return list_session_records()


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get current session state, including all company states."""
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    last_state = active.last_state if active else None

    response = dict(rec)
    if last_state:
        # Serialize company states (convert enums to values)
        company_states = {}
        for cid, cs in last_state.get("company_states", {}).items():
            cs_dict = dict(cs) if isinstance(cs, dict) else {}
            # Normalize status enum → string value
            status = cs_dict.get("status")
            if status is not None:
                cs_dict["status"] = _status_value(status)
            company_states[cid] = cs_dict
        response["company_states"] = company_states
        response["total_cost_usd"] = last_state.get("total_cost_usd", 0.0)
        response["awaiting_persona_selection"] = (
            active.awaiting_persona_selection if active else False
        )

    return response

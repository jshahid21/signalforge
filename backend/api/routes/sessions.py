"""Session routes — POST /sessions, GET /sessions, GET /sessions/{id}."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.api.session_store import (
    ActiveSession,
    create_session_record,
    generate_session_id,
    get_active_session,
    get_session_record,
    list_session_records,
    register_session,
    update_session_record,
)
from backend.api.websocket import manager
from backend.config.loader import load_config
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


async def _run_pipeline_task(
    session_id: str,
    initial_state: AgentState,
    checkpointer: Any,
) -> None:
    """Background task: run the pipeline and emit WebSocket events."""
    from backend.pipeline import build_pipeline

    active = get_active_session(session_id)
    if active is None:
        return

    graph = build_pipeline(checkpointer=checkpointer)
    active.graph = graph
    config = {"configurable": {"thread_id": session_id}}

    try:
        config_obj = load_config()
        max_budget = config_obj.session_budget.max_usd

        # Emit start event
        await manager.broadcast(session_id, {
            "type": "pipeline_started",
            "session_id": session_id,
        })

        # Run pipeline — may pause at HITL interrupt
        result = await graph.ainvoke(initial_state, config=config)
        active.last_state = result

        # Check for HITL pause
        awaiting = {}
        for company_id, cs in result.get("company_states", {}).items():
            if cs.get("current_stage") == "awaiting_persona_selection":
                awaiting[company_id] = cs.get("generated_personas", [])

        if awaiting:
            active.awaiting_persona_selection = True
            update_session_record(session_id, "awaiting_human")
            await manager.broadcast_hitl_required(session_id, awaiting)
        else:
            update_session_record(session_id, "completed")
            await manager.broadcast_pipeline_complete(session_id)

        # Budget warning: if total cost >= 80% of max
        total_cost = result.get("total_cost_usd", 0.0)
        if max_budget > 0 and (total_cost / max_budget) >= 0.8:
            await manager.broadcast_budget_warning(
                session_id,
                pct_used=round((total_cost / max_budget) * 100, 1),
            )

        # Emit stage updates for completed companies
        for company_id, cs in result.get("company_states", {}).items():
            await manager.broadcast_stage_update(
                session_id,
                company_id=company_id,
                stage=cs.get("current_stage", "done"),
                status=str(cs.get("status", "completed")),
            )

    except Exception as exc:
        err_msg = str(exc)
        update_session_record(session_id, "failed", error_message=err_msg)
        await manager.broadcast_error(session_id, err_msg)


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: StartSessionRequest,
    background_tasks: BackgroundTasks,
) -> SessionResponse:
    """Start a new pipeline session.

    Creates a session record and starts the pipeline as a background task.
    Returns session_id immediately; use GET /sessions/{id} to poll status.
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

    # Set up AsyncSqliteSaver checkpointer
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from backend.api.session_store import _sessions_db_path
    checkpointer = AsyncSqliteSaver.from_conn_string(_sessions_db_path())
    await checkpointer.__aenter__()

    active = ActiveSession(session_id=session_id)
    register_session(active)

    # Start pipeline in background
    task = asyncio.create_task(
        _run_pipeline_task(session_id, initial_state, checkpointer)
    )
    active.task = task

    rec = get_session_record(session_id)
    return SessionResponse(
        session_id=session_id,
        status="running",
        company_names=body.company_names,
        created_at=rec["created_at"] if rec else None,
    )


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
        response["company_states"] = {
            cid: dict(cs)
            for cid, cs in last_state.get("company_states", {}).items()
        }
        response["total_cost_usd"] = last_state.get("total_cost_usd", 0.0)
        response["awaiting_persona_selection"] = active.awaiting_persona_selection if active else False

    return response

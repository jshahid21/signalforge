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
    get_session_record,
    list_session_records,
    load_and_register_session,
    register_session,
    save_session_state,
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
    company_states: Optional[dict] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


def _status_value(status: Any) -> str:
    """Serialize a PipelineStatus enum or string to its plain string value."""
    if isinstance(status, PipelineStatus):
        return status.value
    return str(status)


# List fields that must be accumulated (not overwritten) across parallel chunks.
_APPEND_FIELDS = frozenset({
    "completed_company_ids",
    "failed_company_ids",
    "active_company_ids",
    "awaiting_review",
    "execution_log",
    "final_drafts",
})


def _merge_chunk(final_state: dict, node_output: dict) -> None:
    """Merge a streaming chunk into final_state, respecting LangGraph reducers.

    Mirrors the AgentState reducers:
    - company_states: merge_dict  → update, don't overwrite
    - list fields:   append_list → extend, deduplicate
    - total_cost_usd: add_float  → accumulate
    - all other keys:            → last-write wins
    """
    for key, value in node_output.items():
        if key == "company_states" and isinstance(value, dict):
            final_state.setdefault("company_states", {}).update(value)
        elif key == "total_cost_usd" and isinstance(value, (int, float)):
            final_state["total_cost_usd"] = final_state.get("total_cost_usd", 0.0) + value
        elif key in _APPEND_FIELDS and isinstance(value, list):
            existing: list = final_state.get(key, [])
            final_state[key] = existing + [x for x in value if x not in existing]
        else:
            final_state[key] = value


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

        graph = build_pipeline(checkpointer=None)
        active.checkpointer = None

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
                        session_id, company_id, stage, status, company_state=cs
                    )
                _merge_chunk(final_state, node_output)

        active.last_state = final_state
        save_session_state(session_id, final_state)

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
        import logging, traceback
        logging.getLogger(__name__).error(
            "Pipeline failed for session %s: %s\n%s",
            session_id, exc, traceback.format_exc()
        )
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

    from backend.agents.orchestrator import normalize_company_name

    rec = get_session_record(session_id)
    # Pre-populate company_states with names so the frontend can display them immediately
    initial_company_states = {
        normalize_company_name(name): {"company_id": normalize_company_name(name), "company_name": name, "status": "pending"}
        for name in body.company_names
    }
    return SessionResponse(
        session_id=session_id,
        status="running",
        company_names=body.company_names,
        company_states=initial_company_states,
        created_at=rec["created_at"] if rec else None,
    )


@router.post("/{session_id}/resume", status_code=410)
async def resume_session(session_id: str) -> dict:
    """Resume-after-restart is no longer supported.

    The session checkpointer was switched to an in-process MemorySaver to avoid
    LangGraph serialization issues with Send objects at the HITL interrupt.
    MemorySaver state does not survive process restarts, so rehydrating a session
    from disk is impossible. This endpoint now returns HTTP 410 Gone.

    For HITL persona selection, use POST
    /sessions/{id}/companies/{cid}/personas/confirm — that path does not rely on
    the checkpointer and works across the same process lifetime.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Resume-after-restart is no longer supported. Sessions use an "
            "in-memory checkpointer and cannot be resumed across process "
            "restarts. Start a new session instead."
        ),
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
    if active is None or active.last_state is None:
        active = load_and_register_session(session_id)
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

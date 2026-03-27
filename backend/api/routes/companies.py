"""Company routes — GET /sessions/{id}/companies, POST .../retry."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.api.session_store import get_active_session, get_session_record

router = APIRouter(prefix="/sessions/{session_id}/companies", tags=["companies"])


@router.get("")
async def list_companies(session_id: str) -> dict:
    """Return all company states for a session."""
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        return {"company_states": {}, "company_names": rec.get("company_names", [])}

    company_states = {
        cid: dict(cs)
        for cid, cs in active.last_state.get("company_states", {}).items()
    }
    return {
        "company_states": company_states,
        "company_names": rec.get("company_names", []),
    }


@router.get("/{company_id}")
async def get_company(session_id: str, company_id: str) -> dict:
    """Return a single company's state."""
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Company not found")

    cs = active.last_state.get("company_states", {}).get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    return dict(cs)


@router.post("/{company_id}/retry", status_code=202)
async def retry_company(session_id: str, company_id: str) -> dict:
    """Retry a failed company pipeline (not supported in v1 — reserved).

    In v1, only full session retry is supported. This endpoint is reserved
    for future per-company retry functionality.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Company not found")

    cs = active.last_state.get("company_states", {}).get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    # v1: return current state with a retry_not_supported message
    return {
        "message": "Per-company retry is not supported in v1. Submit a new session to retry.",
        "company_id": company_id,
        "current_status": str(cs.get("status", "unknown")),
    }

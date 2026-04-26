"""Chat routes — SSE streaming chat assistant (spec §5.11)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.api.session_store import get_active_session, get_session_record

router = APIRouter(
    prefix="/sessions/{session_id}/companies/{company_id}/chat",
    tags=["chat"],
)


class ChatRequest(BaseModel):
    """User turn for the per-company chat assistant SSE endpoint."""

    message: str
    conversation_history: list[dict] = []
    active_persona_id: Optional[str] = None


@router.post("")
async def chat(
    session_id: str,
    company_id: str,
    body: ChatRequest,
) -> EventSourceResponse:
    """Streaming chat with the Chat Assistant for a specific company.

    Returns an SSE stream. Each event is a text chunk from the LLM.
    The stream ends with a [DONE] event.

    Context:
        The assistant receives the full CompanyState as context.
        It is read-only — it cannot trigger pipeline re-runs.
    """
    rec = get_session_record(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Session not found")

    active = get_active_session(session_id)
    if active is None or active.last_state is None:
        raise HTTPException(status_code=404, detail="Session not active")

    cs = active.last_state.get("company_states", {}).get(company_id)
    if cs is None:
        raise HTTPException(status_code=404, detail="Company not found")

    from backend.agents.chat_assistant import stream_chat_response
    from backend.config.loader import load_config

    config = load_config()

    async def event_generator():
        try:
            async for chunk in stream_chat_response(
                cs=cs,  # type: ignore[arg-type]
                user_message=body.message,
                conversation_history=body.conversation_history,
                llm_model=config.api_keys.llm_model,
                active_persona_id=body.active_persona_id,
            ):
                yield {"data": chunk}
            yield {"data": "[DONE]"}
        except Exception as exc:
            yield {"data": f"[ERROR] {exc}"}

    return EventSourceResponse(event_generator())

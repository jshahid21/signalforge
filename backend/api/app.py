"""FastAPI application — routes, WebSocket, and middleware."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.api.routes import (
    chat,
    companies,
    drafts,
    memory,
    personas,
    sessions,
    settings,
)
from backend.api.websocket import manager
from backend.config.loader import is_first_run, load_config, save_config

app = FastAPI(title="SignalForge API", version="0.1.0")

# CORS — allow frontend dev server (Vite :5173) and any other configured origin
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(sessions.router)
app.include_router(companies.router)
app.include_router(personas.router)
app.include_router(drafts.router)
app.include_router(settings.router)
app.include_router(memory.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/setup")
async def setup_status() -> dict[str, bool]:
    """Return first-run flag so the UI can trigger the Setup Wizard."""
    return {"first_run": is_first_run()}


@app.get("/config")
async def get_config() -> dict:
    """Return current config (used by Setup Wizard to populate form)."""
    return load_config().model_dump()


@app.post("/config")
async def update_config(data: dict) -> dict[str, str]:
    """Persist updated config from Setup Wizard."""
    from backend.config.loader import SignalForgeConfig

    try:
        config = SignalForgeConfig.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    save_config(config)
    return {"status": "saved"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time pipeline progress events.

    Connect to ws://<host>/ws/<session_id> to receive events for a session.

    Event types:
        - pipeline_started: pipeline begun
        - stage_update: { company_id, stage, status } — emitted at each stage
        - hitl_required: { awaiting_persona_selection: {company_id: [personas]} }
        - budget_warning: { pct_used: 82.5 }
        - pipeline_complete: pipeline finished
        - error: { message: "..." }
    """
    await manager.connect(websocket, session_id)
    try:
        # Keep connection alive — client can also send messages (ignored in v1)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)

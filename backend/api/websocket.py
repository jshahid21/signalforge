"""WebSocket connection manager for real-time pipeline progress events.

Events format:
    { "type": "stage_update", "company_id": "stripe", "stage": "research", "status": "running" }
    { "type": "pipeline_complete", "session_id": "..." }
    { "type": "hitl_required", "session_id": "...", "company_id": "...", "personas": [...] }
    { "type": "budget_warning", "session_id": "...", "pct_used": 82.5 }
    { "type": "error", "session_id": "...", "message": "..." }
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections per session."""

    def __init__(self) -> None:
        # session_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        conns = self._connections.get(session_id, set())
        conns.discard(websocket)
        if not conns:
            self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, event: dict[str, Any]) -> None:
        """Send an event JSON to all clients connected to this session."""
        conns = self._connections.get(session_id, set())
        if not conns:
            return
        message = json.dumps(event)
        dead: list[WebSocket] = []
        for ws in list(conns):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, session_id)

    async def broadcast_stage_update(
        self,
        session_id: str,
        company_id: str,
        stage: str,
        status: str,
    ) -> None:
        await self.broadcast(session_id, {
            "type": "stage_update",
            "session_id": session_id,
            "company_id": company_id,
            "stage": stage,
            "status": status,
        })

    async def broadcast_pipeline_complete(self, session_id: str) -> None:
        await self.broadcast(session_id, {
            "type": "pipeline_complete",
            "session_id": session_id,
        })

    async def broadcast_hitl_required(
        self,
        session_id: str,
        awaiting: dict[str, list],
    ) -> None:
        await self.broadcast(session_id, {
            "type": "hitl_required",
            "session_id": session_id,
            "awaiting_persona_selection": awaiting,
        })

    async def broadcast_budget_warning(
        self,
        session_id: str,
        pct_used: float,
    ) -> None:
        await self.broadcast(session_id, {
            "type": "budget_warning",
            "session_id": session_id,
            "pct_used": pct_used,
        })

    async def broadcast_error(self, session_id: str, message: str) -> None:
        await self.broadcast(session_id, {
            "type": "error",
            "session_id": session_id,
            "message": message,
        })


# Global connection manager (singleton)
manager = ConnectionManager()


async def drain_event_queue(session_id: str, queue: asyncio.Queue) -> None:
    """Drain events from the queue and broadcast to WebSocket clients.

    Runs as a background coroutine until None sentinel is received.
    """
    while True:
        event = await queue.get()
        if event is None:
            break
        await manager.broadcast(session_id, event)
        queue.task_done()

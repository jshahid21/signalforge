"""Session store for SignalForge API — session metadata + in-memory registry.

The session store provides two layers:
1. SQLite session metadata (SQLAlchemy) — persists run status, company list,
   seller profile, cost snapshot, and the latest AgentState JSON so reopened
   sessions can be rehydrated for read-only views.
2. In-memory session registry — tracks active pipeline tasks per session. The
   LangGraph checkpointer (when used) is also an in-process MemorySaver, so
   sessions do NOT survive process restarts.

Session lifecycle:
    POST /sessions → create_session_record() → start background task → emit WS events
    GET /sessions/{id} → get_session_record() + optional load_and_register_session()
    HITL gate → graph returns awaiting flag → status set to "awaiting_human"
    POST .../personas/confirm → synthesis + draft run directly (not via graph)
    Pipeline finishes → update_session_record() → completed | partial | failed
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ---------------------------------------------------------------------------
# Session metadata SQLite model
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class SessionRecord(_Base):
    """Metadata for a pipeline session."""

    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True)
    status = Column(String(32), default="running")     # running | awaiting_human | completed | partial | failed
    company_names_json = Column(Text, default="[]")     # JSON list of company names
    seller_profile_json = Column(Text, default="{}")    # JSON seller profile
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    state_json = Column(Text, nullable=True)            # Full AgentState snapshot (JSON)


# ---------------------------------------------------------------------------
# SQLAlchemy sync engine for session metadata
# ---------------------------------------------------------------------------

_meta_engine = None
_MetaSession = None


def _meta_db_path() -> Path:
    override = os.environ.get("SIGNALFORGE_SESSION_DB_PATH")
    if override:
        return Path(override)
    return Path.home() / ".signalforge" / "sessions_meta.db"


def _init_meta_db() -> None:
    global _meta_engine, _MetaSession
    path = _meta_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _meta_engine = create_engine(f"sqlite:///{path}", echo=False)
    _Base.metadata.create_all(_meta_engine)
    # Add state_json column to existing DBs that predate this column
    with _meta_engine.connect() as conn:
        from sqlalchemy import text
        try:
            conn.execute(text("ALTER TABLE sessions ADD COLUMN state_json TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
    _MetaSession = sessionmaker(bind=_meta_engine)


def _get_meta_session():
    if _MetaSession is None:
        _init_meta_db()
    return _MetaSession()


def create_session_record(
    session_id: str,
    company_names: list[str],
    seller_profile: dict,
) -> None:
    """Create a session metadata record in SQLite."""
    with _get_meta_session() as s:
        record = SessionRecord(
            session_id=session_id,
            status="running",
            company_names_json=json.dumps(company_names),
            seller_profile_json=json.dumps(seller_profile),
        )
        s.add(record)
        s.commit()


def get_session_record(session_id: str) -> Optional[dict]:
    """Return session metadata as a dict, or None if not found."""
    with _get_meta_session() as s:
        rec = s.get(SessionRecord, session_id)
        if rec is None:
            return None
        return {
            "session_id": rec.session_id,
            "status": rec.status,
            "company_names": json.loads(rec.company_names_json or "[]"),
            "seller_profile": json.loads(rec.seller_profile_json or "{}"),
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
            "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
            "error_message": rec.error_message,
        }


def list_session_records() -> list[dict]:
    """List all sessions (most recent first)."""
    with _get_meta_session() as s:
        records = s.query(SessionRecord).order_by(SessionRecord.created_at.desc()).all()
        return [
            {
                "session_id": r.session_id,
                "status": r.status,
                "company_names": json.loads(r.company_names_json or "[]"),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]


def update_session_record(
    session_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Update session status in metadata DB."""
    with _get_meta_session() as s:
        rec = s.get(SessionRecord, session_id)
        if rec is None:
            return
        rec.status = status
        # Terminal session statuses stamp completed_at. Keep this list in sync
        # with the PipelineStatus enum's terminal values.
        if status in ("completed", "failed", "partial"):
            rec.completed_at = datetime.now(timezone.utc)
        if error_message:
            rec.error_message = error_message
        s.commit()


def _serialize_state(state: dict) -> str:
    """Serialize AgentState to JSON, converting enums to their string values."""
    import enum

    def _default(obj: Any) -> Any:
        if isinstance(obj, enum.Enum):
            return obj.value
        raise TypeError(f"Not serializable: {type(obj)}")

    return json.dumps(state, default=_default)


def save_session_state(session_id: str, state: dict) -> None:
    """Persist the full AgentState snapshot to the session record."""
    try:
        state_json = _serialize_state(state)
    except Exception:
        return  # Don't crash the pipeline on serialization failure

    with _get_meta_session() as s:
        rec = s.get(SessionRecord, session_id)
        if rec is None:
            return
        rec.state_json = state_json
        s.commit()


def load_session_state(session_id: str) -> Optional[dict]:
    """Load persisted AgentState from DB, or None if not saved yet."""
    with _get_meta_session() as s:
        rec = s.get(SessionRecord, session_id)
        if rec is None or not rec.state_json:
            return None
        try:
            return json.loads(rec.state_json)
        except Exception:
            return None


def load_and_register_session(session_id: str) -> Optional["ActiveSession"]:
    """Load a completed session's state from DB and register it in memory.

    Returns the ActiveSession if the state was found and registered, else None.
    This makes all in-memory endpoints (regenerate draft, approve, etc.) work
    on sessions that were completed in a previous server run.
    """
    state = load_session_state(session_id)
    if state is None:
        return None
    active = ActiveSession(session_id=session_id, last_state=state)
    register_session(active)
    return active


# ---------------------------------------------------------------------------
# In-memory LangGraph checkpointer
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_async_checkpointer() -> AsyncGenerator[Any, None]:
    """Context manager that yields an in-process MemorySaver checkpointer.

    AsyncSqliteSaver could not serialize LangGraph Send objects produced at the
    HITL gate. HITL resume was subsequently moved out of graph (see
    `/sessions/.../personas/confirm`), so disk persistence of graph state is no
    longer required — and no longer available across process restarts.
    """
    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()


# ---------------------------------------------------------------------------
# In-memory session registry
# ---------------------------------------------------------------------------


@dataclass
class ActiveSession:
    """Tracks a running pipeline task and its event queue."""

    session_id: str
    task: Optional[asyncio.Task] = None
    event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    graph: Any = None                    # compiled LangGraph graph
    checkpointer: Any = None             # MemorySaver instance — must be reused for resume
    last_state: Optional[dict] = None   # most recent AgentState snapshot
    awaiting_persona_selection: bool = False


# Global registry: session_id → ActiveSession
_registry: dict[str, ActiveSession] = {}


def get_active_session(session_id: str) -> Optional[ActiveSession]:
    return _registry.get(session_id)


def register_session(session: ActiveSession) -> None:
    _registry[session.session_id] = session


def deregister_session(session_id: str) -> None:
    _registry.pop(session_id, None)


def generate_session_id() -> str:
    return str(uuid.uuid4())

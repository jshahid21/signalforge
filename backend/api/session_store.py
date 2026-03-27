"""Session store for SignalForge API — LangGraph AsyncSqliteSaver + session metadata.

The session store provides two layers:
1. LangGraph AsyncSqliteSaver — stores checkpointed graph state for HITL interrupt/resume.
   Database: ~/.signalforge/sessions.db
2. In-memory session registry — tracks active pipeline tasks and event queues per session.

Session lifecycle:
    POST /sessions → create_session() → start background task → emit events
    GET /sessions/{id} → get_session_state() → reads from checkpointer
    HITL gate → pipeline pauses at interrupt() → state checkpointed
    POST .../personas/confirm → resume_session() → Command(resume=...) resumes graph
    Pipeline completes → update_session_status() → mark completed
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
    status = Column(String(32), default="running")     # running | awaiting_human | completed | failed
    company_names_json = Column(Text, default="[]")     # JSON list of company names
    seller_profile_json = Column(Text, default="{}")    # JSON seller profile
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


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
        if status in ("completed", "failed"):
            rec.completed_at = datetime.now(timezone.utc)
        if error_message:
            rec.error_message = error_message
        s.commit()


# ---------------------------------------------------------------------------
# AsyncSqliteSaver for LangGraph checkpointing
# ---------------------------------------------------------------------------


def _sessions_db_path() -> str:
    override = os.environ.get("SIGNALFORGE_SESSION_DB_PATH")
    if override:
        return override
    path = Path.home() / ".signalforge" / "sessions.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@asynccontextmanager
async def get_async_checkpointer() -> AsyncGenerator[Any, None]:
    """Context manager that yields an AsyncSqliteSaver checkpointer."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    db_path = _sessions_db_path()
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        yield checkpointer


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

"""SQLite database setup for the SignalForge memory store.

Database file: ~/.signalforge/memory.db
Override path via SIGNALFORGE_DB_PATH env var (useful for testing).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models.memory import Base

_engine = None
_SessionLocal = None


def _db_path() -> Path:
    override = os.environ.get("SIGNALFORGE_DB_PATH")
    if override:
        return Path(override)
    return Path.home() / ".signalforge" / "memory.db"


def init() -> None:
    """Create the database and all tables. Safe to call multiple times."""
    global _engine, _SessionLocal
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session. Caller is responsible for closing it."""
    if _SessionLocal is None:
        init()
    return _SessionLocal()

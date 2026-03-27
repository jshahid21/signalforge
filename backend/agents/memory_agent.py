"""Memory Agent — persist approved drafts and retrieve for few-shot injection (spec §5.10, §12).

Write: triggered when user approves a draft in the UI.
Read: queried by Draft Agent to inject up to 2 recent examples for tone consistency.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend import db
from backend.models.memory import MemoryRecord, MemoryRecordORM
from backend.models.state import CompanyState, Draft, Persona, QualifiedSignal, SynthesisOutput


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def write_memory_record(
    company_name: str,
    persona: Persona,
    draft: Draft,
    qualified_signal: QualifiedSignal | None,
    synthesis: SynthesisOutput | None,
) -> MemoryRecord:
    """Persist an approved draft to the memory store. Returns the saved MemoryRecord.

    Called when the user approves a draft in the UI.
    """
    signal_summary = qualified_signal["summary"] if qualified_signal else ""
    technical_context = synthesis["technical_context"] if synthesis else ""

    record = MemoryRecord(
        record_id=str(uuid.uuid4()),
        company_name=company_name,
        persona_title=persona["title"],
        signal_summary=signal_summary,
        technical_context=technical_context,
        draft_subject=draft["subject_line"],
        draft_body=draft["body"],
        approved_at=_now_iso(),
        used_as_example=0,
    )

    with db.get_session() as session:
        orm_record = MemoryRecordORM.from_dataclass(record)
        session.add(orm_record)
        session.commit()

    return record


def get_few_shot_examples(limit: int = 2) -> list[MemoryRecord]:
    """Retrieve the most recent approved drafts for few-shot injection.

    Returns up to `limit` records ordered by approved_at descending.
    Also increments used_as_example counter for each returned record.
    """
    with db.get_session() as session:
        orm_records = (
            session.query(MemoryRecordORM)
            .order_by(MemoryRecordORM.approved_at.desc())
            .limit(limit)
            .all()
        )
        records = [r.to_dataclass() for r in orm_records]

        # Increment usage counter
        for orm_record in orm_records:
            orm_record.used_as_example = (orm_record.used_as_example or 0) + 1
        session.commit()

    return records


def list_all_memory_records() -> list[MemoryRecord]:
    """Return all memory records ordered by approved_at descending. Used by Settings UI."""
    with db.get_session() as session:
        orm_records = (
            session.query(MemoryRecordORM)
            .order_by(MemoryRecordORM.approved_at.desc())
            .all()
        )
        return [r.to_dataclass() for r in orm_records]


def delete_memory_record(record_id: str) -> bool:
    """Delete a memory record by ID. Returns True if found and deleted."""
    with db.get_session() as session:
        record = session.query(MemoryRecordORM).filter_by(record_id=record_id).first()
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True

"""MemoryRecord — dataclass + SQLAlchemy ORM model for the memory store.

Stores approved drafts for few-shot injection into future draft generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


@dataclass
class MemoryRecord:
    """Python dataclass representation of a memory record."""
    record_id: str
    company_name: str
    persona_title: str
    signal_summary: str
    technical_context: str
    draft_subject: str
    draft_body: str
    approved_at: str            # ISO timestamp
    used_as_example: int = field(default=0)  # Count of times injected as few-shot example


class MemoryRecordORM(Base):
    """SQLAlchemy ORM model for persisting MemoryRecord to SQLite."""
    __tablename__ = "memory_records"

    record_id = Column(String, primary_key=True)
    company_name = Column(String, nullable=False)
    persona_title = Column(String, nullable=False)
    signal_summary = Column(String, nullable=False)
    technical_context = Column(String, nullable=False)
    draft_subject = Column(String, nullable=False)
    draft_body = Column(String, nullable=False)
    approved_at = Column(String, nullable=False)
    used_as_example = Column(Integer, nullable=False, default=0)

    def to_dataclass(self) -> MemoryRecord:
        """Convert this ORM row into the plain ``MemoryRecord`` dataclass for use outside SQLAlchemy."""
        return MemoryRecord(
            record_id=self.record_id,
            company_name=self.company_name,
            persona_title=self.persona_title,
            signal_summary=self.signal_summary,
            technical_context=self.technical_context,
            draft_subject=self.draft_subject,
            draft_body=self.draft_body,
            approved_at=self.approved_at,
            used_as_example=self.used_as_example,
        )

    @classmethod
    def from_dataclass(cls, record: MemoryRecord) -> "MemoryRecordORM":
        """Build an ORM row from a ``MemoryRecord`` dataclass — does not add it to a session."""
        return cls(
            record_id=record.record_id,
            company_name=record.company_name,
            persona_title=record.persona_title,
            signal_summary=record.signal_summary,
            technical_context=record.technical_context,
            draft_subject=record.draft_subject,
            draft_body=record.draft_body,
            approved_at=record.approved_at,
            used_as_example=record.used_as_example,
        )

"""Tests for Memory Agent — write/read memory records and few-shot retrieval."""
from __future__ import annotations

import os
import tempfile

import pytest

from backend.agents.memory_agent import (
    delete_memory_record,
    get_few_shot_examples,
    list_all_memory_records,
    write_memory_record,
)
from backend.models.enums import SignalTier
from backend.models.state import (
    Draft,
    Persona,
    QualifiedSignal,
    SynthesisOutput,
)


def _make_persona(persona_id: str = "p1", title: str = "Head of Platform Engineering") -> Persona:
    return Persona(
        persona_id=persona_id,
        title=title,
        targeting_reason="Owns infra.",
        role_type="technical_buyer",
        seniority_level="director",
        priority_score=0.9,
        is_custom=False,
        is_edited=False,
    )


def _make_draft(persona_id: str = "p1", version: int = 1) -> Draft:
    return Draft(
        draft_id=f"draft-{persona_id}-{version}",
        company_id="stripe",
        persona_id=persona_id,
        subject_line="Scaling Kubernetes at Stripe — infrastructure signal",
        body="Your platform team is aggressively hiring SRE and Kubernetes engineers...",
        confidence_score=75.0,
        approved=True,
        version=version,
    )


def _make_qualified_signal() -> QualifiedSignal:
    return QualifiedSignal(
        company_id="stripe",
        summary="Hiring platform engineers for kubernetes infrastructure.",
        signal_type="job_posting",
        keywords_matched=["kubernetes"],
        deterministic_score=0.6,
        llm_severity_score=0.75,
        composite_score=0.69,
        tier_used=SignalTier.TIER_1,
        raw_signals=[],
        qualified=True,
        disqualification_reason=None,
        partial=False,
        signal_ambiguity_score=0.25,
    )


def _make_synthesis() -> SynthesisOutput:
    return SynthesisOutput(
        core_pain_point="Kubernetes at capacity.",
        technical_context="Uses kubernetes for payments infrastructure.",
        solution_alignment="Container orchestration addresses scaling.",
        persona_targeting="Platform lead owns this.",
        buyer_relevance="Operational risk and cost.",
        value_hypothesis="Reduce incidents by 40%.",
        risk_if_ignored="SLA breaches at scale.",
    )


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets a fresh, isolated SQLite database."""
    db_path = str(tmp_path / "test_memory.db")
    os.environ["SIGNALFORGE_DB_PATH"] = db_path
    # Reset db module state
    import backend.db as db_module
    db_module._engine = None
    db_module._SessionLocal = None
    yield db_path
    os.environ.pop("SIGNALFORGE_DB_PATH", None)
    db_module._engine = None
    db_module._SessionLocal = None


class TestWriteMemoryRecord:
    def test_write_returns_memory_record(self) -> None:
        record = write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=_make_qualified_signal(),
            synthesis=_make_synthesis(),
        )
        assert record.record_id
        assert record.company_name == "Stripe"
        assert record.persona_title == "Head of Platform Engineering"
        assert record.draft_subject == "Scaling Kubernetes at Stripe — infrastructure signal"
        assert record.approved_at

    def test_write_persists_to_db(self) -> None:
        write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=_make_qualified_signal(),
            synthesis=_make_synthesis(),
        )
        records = list_all_memory_records()
        assert len(records) == 1
        assert records[0].company_name == "Stripe"

    def test_signal_summary_stored(self) -> None:
        record = write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=_make_qualified_signal(),
            synthesis=_make_synthesis(),
        )
        assert "kubernetes" in record.signal_summary.lower()

    def test_works_without_signal_or_synthesis(self) -> None:
        record = write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=None,
            synthesis=None,
        )
        assert record.record_id
        assert record.signal_summary == ""
        assert record.technical_context == ""


class TestGetFewShotExamples:
    def test_returns_empty_list_when_no_records(self) -> None:
        examples = get_few_shot_examples(limit=2)
        assert examples == []

    def test_returns_up_to_limit_records(self) -> None:
        for i in range(3):
            write_memory_record(
                company_name=f"Company{i}",
                persona=_make_persona(f"p{i}"),
                draft=_make_draft(f"p{i}"),
                qualified_signal=None,
                synthesis=None,
            )
        examples = get_few_shot_examples(limit=2)
        assert len(examples) == 2

    def test_returns_most_recent_first(self) -> None:
        import time
        for i in range(3):
            write_memory_record(
                company_name=f"Company{i}",
                persona=_make_persona(f"p{i}"),
                draft=_make_draft(f"p{i}"),
                qualified_signal=None,
                synthesis=None,
            )
            time.sleep(0.01)  # Ensure distinct timestamps

        examples = get_few_shot_examples(limit=3)
        # Most recent first — Company2 should be first
        assert examples[0].company_name == "Company2"

    def test_increments_used_as_example_counter(self) -> None:
        write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=None,
            synthesis=None,
        )
        get_few_shot_examples(limit=2)
        get_few_shot_examples(limit=2)
        records = list_all_memory_records()
        assert records[0].used_as_example == 2


class TestDeleteMemoryRecord:
    def test_delete_existing_record_returns_true(self) -> None:
        record = write_memory_record(
            company_name="Stripe",
            persona=_make_persona(),
            draft=_make_draft(),
            qualified_signal=None,
            synthesis=None,
        )
        result = delete_memory_record(record.record_id)
        assert result is True
        assert list_all_memory_records() == []

    def test_delete_nonexistent_record_returns_false(self) -> None:
        result = delete_memory_record("nonexistent-id")
        assert result is False


class TestMemoryIntegration:
    def test_write_then_retrieve_for_few_shot_injection(self) -> None:
        """Write an approved draft, then retrieve it for few-shot injection."""
        write_memory_record(
            company_name="Stripe",
            persona=_make_persona("p1", "Head of Platform Engineering"),
            draft=_make_draft("p1"),
            qualified_signal=_make_qualified_signal(),
            synthesis=_make_synthesis(),
        )
        examples = get_few_shot_examples(limit=2)
        assert len(examples) == 1
        assert examples[0].draft_subject == "Scaling Kubernetes at Stripe — infrastructure signal"
        assert "kubernetes" in examples[0].draft_body.lower()

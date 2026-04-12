"""Tests for Phase 2: Data Models & State Schema."""
from __future__ import annotations

import operator
import os
from pathlib import Path

import pytest

from backend.models.enums import HumanReviewReason, PipelineStatus, SignalTier
from backend.models.memory import MemoryRecord, MemoryRecordORM
from backend.models.state import (
    AgentState,
    CompanyError,
    CompanyState,
    CostMetadata,
    Draft,
    Persona,
    QualifiedSignal,
    RawSignal,
    ResearchResult,
    SellerProfile,
    SolutionMappingOutput,
    SynthesisOutput,
    merge_dict,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_signal_tier_values(self) -> None:
        assert SignalTier.TIER_1 == "tier_1"
        assert SignalTier.TIER_2 == "tier_2"
        assert SignalTier.TIER_3 == "tier_3"

    def test_pipeline_status_values(self) -> None:
        assert PipelineStatus.PENDING == "pending"
        assert PipelineStatus.COMPLETED == "completed"
        assert PipelineStatus.FAILED == "failed"
        assert PipelineStatus.SKIPPED == "skipped"

    def test_human_review_reason_values(self) -> None:
        assert HumanReviewReason.LOW_CONFIDENCE == "low_confidence"
        assert HumanReviewReason.DRAFT_QUALITY == "draft_quality"


# ---------------------------------------------------------------------------
# Core TypedDict instantiation tests
# ---------------------------------------------------------------------------


class TestRawSignal:
    def test_instantiates(self) -> None:
        raw: RawSignal = {
            "source": "jsearch",
            "signal_type": "job_posting",
            "content": "Hiring SRE",
            "url": "https://example.com",
            "published_at": "2026-03-27",
            "tier": SignalTier.TIER_1,
        }
        assert raw["source"] == "jsearch"
        assert raw["tier"] == SignalTier.TIER_1

    def test_optional_fields_can_be_none(self) -> None:
        raw: RawSignal = {
            "source": "tavily",
            "signal_type": "engineering_blog",
            "content": "Blog post",
            "url": None,
            "published_at": None,
            "tier": SignalTier.TIER_2,
        }
        assert raw["url"] is None
        assert raw["published_at"] is None


class TestQualifiedSignal:
    def test_instantiates_with_all_fields(self) -> None:
        raw: RawSignal = {
            "source": "jsearch",
            "signal_type": "job_posting",
            "content": "text",
            "url": None,
            "published_at": None,
            "tier": SignalTier.TIER_1,
        }
        qs: QualifiedSignal = {
            "company_id": "stripe",
            "summary": "Hiring ML engineers",
            "signal_type": "job_posting",
            "keywords_matched": ["ml", "kubernetes"],
            "deterministic_score": 0.6,
            "llm_severity_score": 0.7,
            "composite_score": 0.66,
            "tier_used": SignalTier.TIER_1,
            "raw_signals": [raw],
            "qualified": True,
            "disqualification_reason": None,
        }
        assert qs["company_id"] == "stripe"
        assert qs["qualified"] is True


class TestResearchResult:
    def test_partial_true_when_some_tasks_failed(self) -> None:
        rr: ResearchResult = {
            "company_context": "Context here",
            "tech_stack": None,
            "hiring_signals": None,
            "partial": True,
        }
        assert rr["partial"] is True

    def test_all_optional_fields_none(self) -> None:
        rr: ResearchResult = {
            "company_context": None,
            "tech_stack": None,
            "hiring_signals": None,
            "partial": False,
        }
        assert rr["company_context"] is None


class TestSolutionMappingOutput:
    def test_confidence_score_is_integer(self) -> None:
        sm: SolutionMappingOutput = {
            "core_problem": "Scaling data platform",
            "solution_areas": ["Distributed query execution"],
            "inferred_areas": [],
            "matched_capability_ids": [],
            "confidence_score": 85,
            "reasoning": "Strong hiring signals for data eng",
        }
        assert isinstance(sm["confidence_score"], int)
        assert sm["confidence_score"] == 85

    def test_matched_capability_ids(self) -> None:
        sm: SolutionMappingOutput = {
            "core_problem": "ML platform scaling",
            "solution_areas": ["Model training", "Inference"],
            "inferred_areas": [],
            "matched_capability_ids": ["ml_infra", "data_platform"],
            "confidence_score": 75,
            "reasoning": "Strong match to ML capability",
        }
        assert sm["matched_capability_ids"] == ["ml_infra", "data_platform"]


class TestPersona:
    def test_role_types(self) -> None:
        for role in ("economic_buyer", "technical_buyer", "influencer", "blocker"):
            p: Persona = {
                "persona_id": "p1",
                "title": "Head of Platform",
                "targeting_reason": "Signal match",
                "role_type": role,
                "seniority_level": "director",
                "priority_score": 0.8,
                "is_custom": False,
                "is_edited": False,
            }
            assert p["role_type"] == role

    def test_seniority_levels(self) -> None:
        for seniority in ("exec", "director", "manager", "ic"):
            p: Persona = {
                "persona_id": "p2",
                "title": "Engineer",
                "targeting_reason": "reason",
                "role_type": "technical_buyer",
                "seniority_level": seniority,
                "priority_score": 0.5,
                "is_custom": False,
                "is_edited": False,
            }
            assert p["seniority_level"] == seniority


class TestDraft:
    def test_version_default(self) -> None:
        d: Draft = {
            "draft_id": "d1",
            "company_id": "stripe",
            "persona_id": "p1",
            "subject_line": "Re: your infra scaling",
            "body": "Hi...",
            "confidence_score": 0.82,
            "approved": False,
            "version": 1,
        }
        assert d["version"] == 1

    def test_version_increments(self) -> None:
        d: Draft = {
            "draft_id": "d1",
            "company_id": "stripe",
            "persona_id": "p1",
            "subject_line": "Re: your infra scaling",
            "body": "Hi v2...",
            "confidence_score": 0.82,
            "approved": False,
            "version": 2,
        }
        assert d["version"] == 2


# ---------------------------------------------------------------------------
# CompanyState tests
# ---------------------------------------------------------------------------


class TestCompanyState:
    def _make_cost_metadata(self) -> CostMetadata:
        return {
            "tier_1_calls": 0,
            "tier_2_calls": 0,
            "tier_3_calls": 0,
            "llm_tokens_used": 0,
            "estimated_cost_usd": 0.0,
            "tier_escalation_reasons": [],
        }

    def test_all_optional_fields_default_to_none_or_empty(self) -> None:
        cs: CompanyState = {
            "company_id": "stripe",
            "company_name": "Stripe",
            "status": PipelineStatus.PENDING,
            "current_stage": "init",
            "raw_signals": [],
            "qualified_signal": None,
            "signal_qualified": False,
            "research_result": None,
            "solution_mapping": None,
            "generated_personas": [],
            "selected_personas": [],
            "recommended_outreach_sequence": [],
            "synthesis_outputs": {},
            "drafts": {},
            "cost_metadata": self._make_cost_metadata(),
            "errors": [],
            "human_review_required": False,
            "human_review_reasons": [],
            "override_requested": False,
            "override_reason": None,
            "drafted_under_override": False,
        }
        assert cs["company_id"] == "stripe"
        assert cs["qualified_signal"] is None
        assert cs["generated_personas"] == []
        assert cs["drafts"] == {}


# ---------------------------------------------------------------------------
# AgentState reducer tests
# ---------------------------------------------------------------------------


class TestAgentStateReducers:
    def _make_seller_profile(self) -> SellerProfile:
        return {
            "company_name": "Oracle Cloud Infrastructure",
            "portfolio_summary": "Cloud infra",
            "portfolio_items": ["OCI Compute"],
        }

    def test_total_cost_usd_uses_add_reducer(self) -> None:
        # Verify the Annotated metadata carries operator.add
        import typing
        hints = typing.get_type_hints(AgentState, include_extras=True)
        cost_hint = hints["total_cost_usd"]
        args = typing.get_args(cost_hint)
        # args[0] is the base type (float), args[1] is the reducer function
        assert args[0] is float
        assert args[1] is operator.add

    def test_completed_company_ids_uses_concat_reducer(self) -> None:
        import typing
        hints = typing.get_type_hints(AgentState, include_extras=True)
        hint = hints["completed_company_ids"]
        args = typing.get_args(hint)
        assert args[1] is operator.concat

    def test_failed_company_ids_uses_concat_reducer(self) -> None:
        import typing
        hints = typing.get_type_hints(AgentState, include_extras=True)
        hint = hints["failed_company_ids"]
        args = typing.get_args(hint)
        assert args[1] is operator.concat

    def test_final_drafts_uses_concat_reducer(self) -> None:
        import typing
        hints = typing.get_type_hints(AgentState, include_extras=True)
        hint = hints["final_drafts"]
        args = typing.get_args(hint)
        assert args[1] is operator.concat

    def test_company_states_uses_merge_dict_reducer(self) -> None:
        import typing
        hints = typing.get_type_hints(AgentState, include_extras=True)
        hint = hints["company_states"]
        args = typing.get_args(hint)
        assert args[1] is merge_dict

    def test_add_reducer_accumulates_cost(self) -> None:
        # Simulate two parallel Send() branches adding cost
        cost_a = 0.10
        cost_b = 0.15
        combined = operator.add(cost_a, cost_b)
        assert abs(combined - 0.25) < 1e-9

    def test_concat_reducer_accumulates_ids(self) -> None:
        ids_a = ["stripe"]
        ids_b = ["langchain"]
        combined = operator.concat(ids_a, ids_b)
        assert combined == ["stripe", "langchain"]

    def test_merge_dict_reducer_merges_by_key(self) -> None:
        states_a = {"stripe": {"company_id": "stripe", "status": "running"}}
        states_b = {"langchain": {"company_id": "langchain", "status": "running"}}
        merged = merge_dict(states_a, states_b)
        assert "stripe" in merged
        assert "langchain" in merged

    def test_merge_dict_reducer_no_collision(self) -> None:
        # Two companies updating their own key don't overwrite each other
        states_a = {"stripe": {"company_id": "stripe", "status": "completed"}}
        states_b = {"langchain": {"company_id": "langchain", "status": "failed"}}
        merged = merge_dict(states_a, states_b)
        assert merged["stripe"]["status"] == "completed"
        assert merged["langchain"]["status"] == "failed"

    def test_merge_dict_b_overwrites_a_on_same_key(self) -> None:
        # b takes precedence (update semantics)
        a = {"stripe": {"status": "running"}}
        b = {"stripe": {"status": "completed"}}
        merged = merge_dict(a, b)
        assert merged["stripe"]["status"] == "completed"


# ---------------------------------------------------------------------------
# MemoryRecord tests
# ---------------------------------------------------------------------------


class TestMemoryRecord:
    def test_dataclass_instantiation(self) -> None:
        rec = MemoryRecord(
            record_id="rec-001",
            company_name="Stripe",
            persona_title="Head of Platform Engineering",
            signal_summary="Hiring SRE + Kubernetes",
            technical_context="Multi-cloud infra migration",
            draft_subject="Re: your platform scaling",
            draft_body="Hi ...",
            approved_at="2026-03-27T10:00:00Z",
        )
        assert rec.record_id == "rec-001"
        assert rec.used_as_example == 0  # default

    def test_used_as_example_default_is_zero(self) -> None:
        rec = MemoryRecord(
            record_id="r1",
            company_name="Langchain",
            persona_title="CTO",
            signal_summary="summary",
            technical_context="context",
            draft_subject="subject",
            draft_body="body",
            approved_at="2026-03-27T00:00:00Z",
        )
        assert rec.used_as_example == 0

    def test_orm_round_trip(self) -> None:
        rec = MemoryRecord(
            record_id="r2",
            company_name="Snowflake",
            persona_title="VP Engineering",
            signal_summary="Scaling DW",
            technical_context="Petabyte-scale analytics",
            draft_subject="DW performance",
            draft_body="Hello...",
            approved_at="2026-03-27T00:00:00Z",
            used_as_example=3,
        )
        orm = MemoryRecordORM.from_dataclass(rec)
        assert orm.record_id == "r2"
        assert orm.used_as_example == 3

        back = orm.to_dataclass()
        assert back.company_name == "Snowflake"
        assert back.used_as_example == 3


# ---------------------------------------------------------------------------
# Database init tests
# ---------------------------------------------------------------------------


class TestDbInit:
    def test_creates_table_on_init(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test_memory.db"
        os.environ["SIGNALFORGE_DB_PATH"] = str(db_path)
        try:
            import backend.db as db_module
            db_module._engine = None
            db_module._SessionLocal = None

            db_module.init()
            assert db_path.exists()

            # Verify table was created by inserting and querying a record
            session = db_module.get_session()
            try:
                orm = MemoryRecordORM(
                    record_id="test",
                    company_name="Test Co",
                    persona_title="CTO",
                    signal_summary="signal",
                    technical_context="context",
                    draft_subject="subject",
                    draft_body="body",
                    approved_at="2026-03-27T00:00:00Z",
                    used_as_example=0,
                )
                session.add(orm)
                session.commit()
                fetched = session.get(MemoryRecordORM, "test")
                assert fetched is not None
                assert fetched.company_name == "Test Co"
            finally:
                session.close()
        finally:
            del os.environ["SIGNALFORGE_DB_PATH"]
            db_module._engine = None
            db_module._SessionLocal = None

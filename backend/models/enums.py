"""Enums for the SignalForge pipeline."""
from enum import Enum


class SignalTier(str, Enum):
    """Cost tier of a signal source — drives escalation rules in signal_ingestion (spec §7)."""

    TIER_1 = "tier_1"   # Low cost: job postings, lightweight public signals
    TIER_2 = "tier_2"   # Moderate: web search, blog/engineering signals
    TIER_3 = "tier_3"   # High cost: deep enrichment


class PipelineStatus(str, Enum):
    """Lifecycle status for a company pipeline run (and the parent session)."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    # PARTIAL = session-level terminal state used when some companies in a
    # multi-company run succeed and some fail. Companies themselves remain
    # either COMPLETED or FAILED — PARTIAL only appears on the session record.
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class HumanReviewReason(str, Enum):
    """Reason a company was flagged for human review (spec §5.5)."""

    LOW_CONFIDENCE = "low_confidence"
    SIGNAL_AMBIGUOUS = "signal_ambiguous"
    PERSONA_UNRESOLVED = "persona_unresolved"
    DRAFT_QUALITY = "draft_quality"

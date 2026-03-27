"""Enums for the SignalForge pipeline."""
from enum import Enum


class SignalTier(str, Enum):
    TIER_1 = "tier_1"   # Low cost: job postings, lightweight public signals
    TIER_2 = "tier_2"   # Moderate: web search, blog/engineering signals
    TIER_3 = "tier_3"   # High cost: deep enrichment


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class HumanReviewReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    SIGNAL_AMBIGUOUS = "signal_ambiguous"
    PERSONA_UNRESOLVED = "persona_unresolved"
    DRAFT_QUALITY = "draft_quality"

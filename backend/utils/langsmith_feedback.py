"""LangSmith feedback logging for draft approve/reject events.

Logs structured feedback to LangSmith via client.create_feedback() so that
approval and rejection signals are tied to the LangSmith evaluation system.

Graceful no-op when:
  - LANGCHAIN_TRACING_V2 is not "true"
  - langsmith package is not installed
  - run_id is missing from the draft
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _tracing_enabled() -> bool:
    return os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true"


def log_draft_feedback(
    run_id: Optional[str],
    approved: bool,
    comment: Optional[str] = None,
) -> None:
    """Log draft approve/reject as LangSmith feedback.

    Args:
        run_id: LangSmith run ID from the draft generation trace.
        approved: True for approval, False for rejection/regeneration.
        comment: Optional comment (e.g., override_reason on reject).
    """
    if not _tracing_enabled():
        return
    if not run_id:
        logger.debug("No run_id on draft — skipping LangSmith feedback")
        return

    try:
        from langsmith import Client
    except ImportError:
        logger.debug("langsmith not installed — skipping feedback")
        return

    try:
        client = Client()
        client.create_feedback(
            run_id=run_id,
            key="draft-quality",
            score=1.0 if approved else 0.0,
            comment=comment,
        )
    except Exception:
        logger.warning("Failed to log LangSmith feedback for run %s", run_id, exc_info=True)


APPROVED_DRAFTS_DATASET = "signalforge-approved-drafts"


def store_approved_draft_as_example(
    *,
    signal_summary: str,
    signal_category: Optional[str],
    persona_title: str,
    persona_role_type: str,
    technical_context: str,
    subject_line: str,
    body: str,
    confidence_score: float,
) -> None:
    """Store an approved draft as a LangSmith dataset example.

    Creates the dataset if it doesn't exist, then adds the example with
    input (signal, persona, context) and output (approved draft text).

    Graceful no-op when tracing is disabled or langsmith is not installed.
    """
    if not _tracing_enabled():
        return

    try:
        from langsmith import Client
    except ImportError:
        logger.debug("langsmith not installed — skipping dataset storage")
        return

    try:
        client = Client()

        # Ensure dataset exists (create_dataset is idempotent on name collision)
        try:
            client.read_dataset(dataset_name=APPROVED_DRAFTS_DATASET)
        except Exception:
            client.create_dataset(
                APPROVED_DRAFTS_DATASET,
                description="Approved drafts for SignalForge evaluation",
            )

        client.create_example(
            inputs={
                "signal_summary": signal_summary,
                "persona_title": persona_title,
                "persona_role_type": persona_role_type,
                "technical_context": technical_context,
            },
            outputs={
                "subject_line": subject_line,
                "body": body,
            },
            metadata={
                "signal_category": signal_category,
                "persona_role_type": persona_role_type,
                "confidence_score": confidence_score,
            },
            dataset_name=APPROVED_DRAFTS_DATASET,
        )
    except Exception:
        logger.warning("Failed to store approved draft as LangSmith example", exc_info=True)

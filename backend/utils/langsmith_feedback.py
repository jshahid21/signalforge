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

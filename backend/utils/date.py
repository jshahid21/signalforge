"""Date utilities — always use these when injecting dates into LLM prompts.

LLMs have training cutoffs and will silently reason from stale dates unless
the real current date is explicitly provided in the prompt.
"""
from datetime import date


def today_str() -> str:
    """Return today's date as an ISO string, e.g. '2026-03-27'."""
    return date.today().isoformat()


def date_context_line() -> str:
    """Single-line date context for injection at the top of LLM prompts."""
    return f"Today's date: {today_str()}. Use this date for all recency assessments — do not use your training cutoff date."

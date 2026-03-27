"""Orchestrator Agent — input validation, slug normalization, and Send() fan-out.

Spec §5.1:
- Validates company list (1–5 entries)
- Normalizes names → company_id slugs
- Detects duplicate slugs and raises descriptive error
- Initializes per-company CompanyState objects
- Routing function dispatches parallel Send("company_pipeline", input) for each company
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from langgraph.types import Send

from backend.config.capability_map import load_capability_map
from backend.config.loader import load_config
from backend.models.enums import PipelineStatus
from backend.models.state import (
    AgentState,
    CompanyInput,
    CompanyState,
    CostMetadata,
)

# Legal suffixes to strip (case-insensitive, per spec §5.1)
_LEGAL_SUFFIXES = [
    "incorporated",
    "corporation",
    "group",
    "corp",
    "inc",
    "llc",
    "ltd",
]


def normalize_company_name(name: str) -> str:
    """Convert a company display name to a stable slug (spec §5.1).

    Steps:
    1. Lowercase
    2. Strip legal suffixes (case-insensitive, word-boundary)
    3. Replace non-alphanumeric chars with '-'
    4. Collapse consecutive '-'
    5. Trim leading/trailing '-'

    Examples:
        "Stripe, Inc."   -> "stripe"
        "Upbound Group"  -> "upbound"
        "stripe.com"     -> "stripe-com"
    """
    s = name.strip().lower()

    # Strip legal suffixes (must be whole word at end, optionally preceded by comma/space/period)
    for suffix in _LEGAL_SUFFIXES:
        pattern = r"[,.\s]+" + re.escape(suffix) + r"[.\s]*$"
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)

    s = s.strip()
    # Replace all non-alphanumeric characters with '-'
    s = re.sub(r"[^a-z0-9]", "-", s)
    # Collapse consecutive '-'
    s = re.sub(r"-+", "-", s)
    # Trim leading/trailing '-'
    s = s.strip("-")
    return s


def validate_companies(companies: list[str]) -> None:
    """Raise ValueError for invalid company lists.

    Checks:
    - Must have 1–5 entries
    - No duplicate slugs after normalization
    """
    if not companies:
        raise ValueError("At least one company name is required.")
    if len(companies) > 5:
        raise ValueError(
            f"Too many companies: {len(companies)}. Maximum is 5."
        )

    slugs: dict[str, str] = {}  # slug → original name
    for name in companies:
        slug = normalize_company_name(name)
        if not slug:
            raise ValueError(f"Company name '{name}' normalizes to an empty slug.")
        if slug in slugs:
            raise ValueError(
                f"Duplicate company detected after normalization: "
                f"'{slugs[slug]}' and '{name}' both resolve to '{slug}'. "
                f"Please remove one."
            )
        slugs[slug] = name


def _make_empty_cost_metadata() -> CostMetadata:
    return CostMetadata(
        tier_1_calls=0,
        tier_2_calls=0,
        tier_3_calls=0,
        llm_tokens_used=0,
        estimated_cost_usd=0.0,
        tier_escalation_reasons=[],
    )


def _make_initial_company_state(name: str) -> CompanyState:
    """Create a fresh CompanyState for a given company name."""
    company_id = normalize_company_name(name)
    return CompanyState(
        company_id=company_id,
        company_name=name,
        status=PipelineStatus.PENDING,
        current_stage="init",
        raw_signals=[],
        qualified_signal=None,
        signal_qualified=False,
        research_result=None,
        solution_mapping=None,
        generated_personas=[],
        selected_personas=[],
        recommended_outreach_sequence=[],
        synthesis_outputs={},
        drafts={},
        cost_metadata=_make_empty_cost_metadata(),
        errors=[],
        human_review_required=False,
        human_review_reasons=[],
        override_requested=False,
        override_reason=None,
        drafted_under_override=False,
    )


def orchestrator_node(state: AgentState) -> dict:
    """Validate input and initialize per-company CompanyState objects.

    Returns AgentState updates (company_states, active_company_ids, pipeline_started_at).
    A routing function (dispatch_companies) then fans out with Send().
    """
    validate_companies(state["target_companies"])

    company_states: dict = {}
    active_ids: list[str] = []

    for name in state["target_companies"]:
        cs = _make_initial_company_state(name)
        company_states[cs["company_id"]] = cs
        active_ids.append(cs["company_id"])

    return {
        "company_states": company_states,
        "active_company_ids": active_ids,
        "pipeline_started_at": datetime.now(timezone.utc).isoformat(),
    }


def dispatch_companies(state: AgentState) -> list[Send]:
    """Routing function: fan out to per-company pipelines via Send().

    Called by conditional_edges after orchestrator_node initializes company states.
    """
    config = load_config()
    capability_map = load_capability_map()
    current_cost = state.get("total_cost_usd", 0.0)

    sends = []
    for company_id, cs in state.get("company_states", {}).items():
        if cs.get("status") != PipelineStatus.PENDING:
            continue
        payload = CompanyInput(
            company_state=cs,
            seller_profile=state["seller_profile"],
            max_budget_usd=config.session_budget.max_usd,
            total_cost_usd_at_dispatch=current_cost,
            capability_map=capability_map,
            jsearch_api_key=config.api_keys.jsearch,
            tavily_api_key=config.api_keys.tavily,
            llm_provider=config.api_keys.llm_provider,
            llm_model=config.api_keys.llm_model,
        )
        sends.append(Send("company_pipeline", payload))

    return sends

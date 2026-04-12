"""LangGraph AgentState and all supporting TypedDicts for SignalForge.

Parallel-safe reducers are applied to fields written by concurrent Send() branches:
- total_cost_usd     → operator.add      (accumulates cost)
- completed_company_ids → operator.concat
- failed_company_ids    → operator.concat
- final_drafts          → operator.concat
- company_states        → merge_dict      (merges by company_id key)
"""
from __future__ import annotations

import operator
from typing import Annotated, Dict, List, Literal, Optional

from typing_extensions import NotRequired, TypedDict

from backend.models.enums import HumanReviewReason, PipelineStatus, SignalTier


# ---------------------------------------------------------------------------
# Reducer helpers
# ---------------------------------------------------------------------------


def merge_dict(a: Dict, b: Dict) -> Dict:
    """Merge two dicts, with b taking precedence. Used for company_states."""
    return {**a, **b}


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


class RawSignal(TypedDict):
    source: str             # e.g., "jsearch", "tavily", "blog"
    signal_type: str        # e.g., "job_posting", "engineering_blog", "funding_news"
    content: str            # Raw text / excerpt
    url: Optional[str]
    published_at: Optional[str]
    tier: SignalTier


class QualifiedSignal(TypedDict):
    company_id: str
    summary: str                    # LLM-generated signal summary
    signal_type: str
    keywords_matched: List[str]
    deterministic_score: float      # 0.0–1.0 keyword-weight score
    llm_severity_score: float       # 0.0–1.0 LLM-assessed severity
    composite_score: float          # Weighted combination of both
    tier_used: SignalTier
    raw_signals: List[RawSignal]
    qualified: bool
    disqualification_reason: Optional[str]
    partial: bool                   # True if LLM scoring failed; deterministic-only fallback
    signal_ambiguity_score: float   # 1 − mean(recency, specificity); used for Tier 2 escalation


class ResearchResult(TypedDict):
    company_context: Optional[str]      # General company/market context
    tech_stack: Optional[List[str]]     # Explicit mentions only; no inference
    hiring_signals: Optional[str]       # Summary of hiring trends
    partial: bool                       # True if some research tasks failed gracefully


class SolutionMappingOutput(TypedDict):
    core_problem: str
    solution_areas: List[str]           # Vendor-agnostic capability categories
    inferred_areas: List[str]           # Subset of solution_areas not in capability map
    confidence_score: int               # 0–100 integer scale (per spec §5.5)
    reasoning: str


class Persona(TypedDict):
    persona_id: str
    title: str                          # e.g., "Head of Platform Engineering"
    targeting_reason: str               # Why this persona is relevant given the signal
    role_type: Literal["economic_buyer", "technical_buyer", "influencer", "blocker"]
    seniority_level: Literal["exec", "director", "manager", "ic"]
    priority_score: float               # 0–1: likelihood this persona should be targeted first
    is_custom: bool                     # True if user-added
    is_edited: bool                     # True if user modified the title


class SynthesisOutput(TypedDict):
    core_pain_point: str
    technical_context: str
    solution_alignment: str
    persona_targeting: str              # Specific to the selected persona
    buyer_relevance: str                # Why THIS persona specifically would care
    value_hypothesis: str               # What outcome this persona is likely optimizing for
    risk_if_ignored: str                # What happens if they don't solve this (urgency signal)


class Draft(TypedDict):
    draft_id: str
    company_id: str
    persona_id: str
    subject_line: str
    body: str
    confidence_score: float             # Inherited from solution mapping
    approved: bool
    version: int                        # Starts at 1; increments on regeneration
    run_id: NotRequired[Optional[str]]  # LangSmith run ID for feedback linkage


class CostMetadata(TypedDict):
    tier_1_calls: int
    tier_2_calls: int
    tier_3_calls: int
    llm_tokens_used: int
    estimated_cost_usd: float
    tier_escalation_reasons: List[str]


class CompanyError(TypedDict):
    stage: str                          # Which agent/stage failed
    error_type: str
    message: str
    recoverable: bool


class SalesPlayDict(TypedDict):
    play: str
    category: str


class ProofPointDict(TypedDict):
    customer: str
    summary: str


class SellerIntelligenceDict(TypedDict, total=False):
    differentiators: List[str]
    sales_plays: List[SalesPlayDict]
    proof_points: List[ProofPointDict]
    competitive_positioning: List[str]
    last_scraped: Optional[str]


class SellerProfile(TypedDict):
    company_name: str
    portfolio_summary: str
    portfolio_items: List[str]
    website_url: NotRequired[Optional[str]]
    seller_intelligence: NotRequired[SellerIntelligenceDict]


# ---------------------------------------------------------------------------
# Per-company state
# ---------------------------------------------------------------------------


class CompanyState(TypedDict):
    # Identity
    company_id: str
    company_name: str

    # Pipeline status
    status: PipelineStatus
    current_stage: str

    # Signal layer
    raw_signals: List[RawSignal]
    qualified_signal: Optional[QualifiedSignal]
    signal_qualified: bool

    # Research layer
    research_result: Optional[ResearchResult]

    # Solution mapping
    solution_mapping: Optional[SolutionMappingOutput]

    # Persona layer
    generated_personas: List[Persona]
    selected_personas: List[str]                        # persona_ids (user-selected)
    recommended_outreach_sequence: List[str]            # Ordered persona_ids (system-suggested)
    persona_signal_category: Optional[str]              # Signal category driving persona selection

    # Synthesis + drafting
    synthesis_outputs: Dict[str, SynthesisOutput]       # keyed by persona_id
    drafts: Dict[str, Draft]                            # keyed by persona_id

    # Cost tracking
    cost_metadata: CostMetadata

    # Error tracking
    errors: List[CompanyError]
    human_review_required: bool
    human_review_reasons: List[HumanReviewReason]

    # HITL override tracking
    override_requested: bool
    override_reason: Optional[str]
    drafted_under_override: bool


# ---------------------------------------------------------------------------
# Global agent state (LangGraph root state)
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    # Input
    target_companies: List[str]
    seller_profile: SellerProfile

    # Per-company isolated states — merge_dict reducer prevents parallel collision
    company_states: Annotated[Dict[str, CompanyState], merge_dict]

    # Global orchestration — use last-write-wins for scalars, concat for lists
    pipeline_started_at: str
    pipeline_completed_at: Optional[str]
    active_company_ids: Annotated[List[str], lambda a, b: list(dict.fromkeys(a + b))]
    completed_company_ids: Annotated[List[str], operator.concat]
    failed_company_ids: Annotated[List[str], operator.concat]

    # Human-in-the-loop flags
    awaiting_persona_selection: Annotated[bool, lambda a, b: a or b]
    awaiting_review: Annotated[List[str], operator.concat]

    # Execution metadata
    execution_log: Annotated[List[str], operator.concat]
    total_cost_usd: Annotated[float, operator.add]

    # Final output
    final_drafts: Annotated[List[Draft], operator.concat]


# ---------------------------------------------------------------------------
# Per-company pipeline input (passed via Send() from orchestrator)
# ---------------------------------------------------------------------------


class CompanyInput(TypedDict):
    """Payload dispatched by orchestrator via Send("company_pipeline", ...).

    Bundles per-company state with global context needed by company agents.
    """
    company_state: CompanyState
    seller_profile: SellerProfile
    max_budget_usd: float
    total_cost_usd_at_dispatch: float   # Snapshot of global cost at dispatch time
    capability_map: Optional[object]    # backend.config.capability_map.CapabilityMap
    jsearch_api_key: str
    tavily_api_key: str
    llm_provider: str
    llm_model: str

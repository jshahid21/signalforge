"""Signal Ingestion Agent — cost-tiered signal acquisition (spec §5.2, §7).

Tier 1 (always): JSearch job postings
Tier 2 (conditional): Tavily web search (engineering blog scan)
Tier 3 (conditional): Deep enrichment (configurable source)

Tier escalation rules (spec §7.1–7.2):
  Tier 2 triggers if ANY of:
    - signal density < 3 (fewer than 3 relevant job postings)
    - deterministic_score == 0 (no capability map keywords matched)
    - signal_ambiguity_score > 0.7

  Tier 3 triggers if ALL of:
    - Tier 2 composite score >= 0.75
    - Enterprise budget indicators present
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.config.capability_map import CapabilityMap
from backend.models.enums import PipelineStatus, SignalTier
from backend.models.state import (
    CompanyError,
    CompanyState,
    CostMetadata,
    RawSignal,
)
from backend.tools.jsearch import JSearchClient
from backend.tools.tavily import TavilySearchClient

# Cost estimates per API call (USD)
_TIER_1_COST_PER_CALL = 0.001
_TIER_2_COST_PER_CALL = 0.005
_TIER_3_COST_PER_CALL = 0.02

# Threshold below which Tier 2 is triggered
_TIER_1_DENSITY_THRESHOLD = 3


def compute_signal_density(
    signals: list[RawSignal],
    keywords: list[str],
) -> int:
    """Count job postings where at least one capability map keyword matches.

    Signal density = count of job postings where at least one keyword appears
    in the job title or description (case-insensitive).
    """
    if not keywords:
        return 0
    count = 0
    lower_keywords = [kw.lower() for kw in keywords]
    for signal in signals:
        if signal.get("signal_type") != "job_posting":
            continue
        content = signal.get("content", "").lower()
        if any(kw in content for kw in lower_keywords):
            count += 1
    return count


def _job_to_raw_signal(job: dict[str, Any]) -> RawSignal:
    """Convert a JSearch job dict to RawSignal."""
    return RawSignal(
        source="jsearch",
        signal_type="job_posting",
        content=f"{job.get('job_title', '')} — {job.get('job_description', '')[:500]}",
        url=job.get("job_apply_link"),
        published_at=job.get("job_posted_at_datetime_utc"),
        tier=SignalTier.TIER_1,
    )


def _search_result_to_raw_signal(result: dict[str, Any], tier: SignalTier) -> RawSignal:
    """Convert a Tavily search result to RawSignal."""
    return RawSignal(
        source="tavily",
        signal_type="engineering_blog",
        content=result.get("content", "")[:1000],
        url=result.get("url"),
        published_at=None,
        tier=tier,
    )


async def run_tier_1(
    company_name: str,
    jsearch_client: JSearchClient,
) -> list[RawSignal]:
    """Acquire Tier 1 signals: JSearch job postings."""
    jobs = await jsearch_client.search_jobs(company_name, days_ago=30)
    return [_job_to_raw_signal(job) for job in jobs]


async def run_tier_2(
    company_name: str,
    tavily_client: TavilySearchClient,
) -> list[RawSignal]:
    """Acquire Tier 2 signals: Tavily web search for engineering blog/infra signals."""
    query = f"{company_name} engineering blog infrastructure OR platform"
    results = await tavily_client.search(query, max_results=10, days=90)
    return [_search_result_to_raw_signal(r, SignalTier.TIER_2) for r in results]


def _should_escalate_to_tier_2(
    raw_signals: list[RawSignal],
    keywords: list[str],
    signal_ambiguity_score: float | None,
) -> tuple[bool, str]:
    """Return (should_escalate, reason) for Tier 2 escalation (spec §7.1).

    Triggers if ANY of:
    - signal density < 3 (fewer than 3 relevant job postings), OR
    - deterministic_score == 0 (no capability map keywords matched in any signal), OR
    - signal_ambiguity_score > 0.7 (LLM scores signal as non-specific or stale)

    NOTE: signal_ambiguity_score requires LLM severity output from a pre-qualification
    step, which is not available during ingestion (chicken-and-egg with qualification).
    It is computed from recency + specificity sub-scores. For Phase 3, it is passed as
    None and checked only when available (e.g., from a prior pipeline run or re-run).
    """
    density = compute_signal_density(raw_signals, keywords)
    if density < _TIER_1_DENSITY_THRESHOLD:
        return True, f"signal density {density} < threshold {_TIER_1_DENSITY_THRESHOLD}"

    if signal_ambiguity_score is not None and signal_ambiguity_score > 0.7:
        return True, f"signal_ambiguity_score {signal_ambiguity_score:.2f} > 0.7"

    return False, ""


def _has_enterprise_indicators(signals: list[RawSignal]) -> bool:
    """Heuristic check for enterprise-scale budget indicators in signals.

    Detects phrases that suggest large engineering investment / enterprise scale.
    Used in Tier 3 escalation threshold check (spec §7.2).
    """
    enterprise_terms = [
        "enterprise", "at scale", "multi-region", "global infrastructure",
        "thousands of", "petabyte", "hyperscale", "platform team",
        "platform engineering", "staff engineer", "principal engineer",
    ]
    combined = " ".join(s.get("content", "") for s in signals).lower()
    return any(term in combined for term in enterprise_terms)


async def run_signal_ingestion(
    cs: CompanyState,
    capability_map: CapabilityMap | None,
    current_total_cost: float,
    max_budget_usd: float,
    jsearch_client: JSearchClient,
    tavily_client: TavilySearchClient,
) -> tuple[CompanyState, float]:
    """Run tiered signal ingestion for one company.

    Returns (updated_company_state, cost_incurred).
    """
    company_name = cs["company_name"]
    cost_incurred = 0.0

    # Budget check before any API call
    if current_total_cost >= max_budget_usd:
        cs = dict(cs)  # type: ignore[assignment]
        cs["status"] = PipelineStatus.FAILED
        cs["errors"] = list(cs.get("errors", [])) + [
            CompanyError(
                stage="signal_ingestion",
                error_type="budget_exceeded",
                message=f"Session budget ${max_budget_usd:.2f} exhausted.",
                recoverable=False,
            )
        ]
        return cs, 0.0  # type: ignore[return-value]

    keywords = capability_map.all_keywords() if capability_map else []

    # --- Tier 1 (always) ---
    try:
        tier_1_signals = await run_tier_1(company_name, jsearch_client)
        cost_incurred += _TIER_1_COST_PER_CALL
        tier_1_calls = 1
    except Exception as exc:
        cs = dict(cs)  # type: ignore[assignment]
        cs["errors"] = list(cs.get("errors", [])) + [
            CompanyError(
                stage="signal_ingestion_tier1",
                error_type=type(exc).__name__,
                message=str(exc),
                recoverable=True,
            )
        ]
        tier_1_signals = []
        tier_1_calls = 0

    all_signals = list(tier_1_signals)
    tier_2_calls = 0
    tier_3_calls = 0
    escalation_reasons: list[str] = []
    cs = dict(cs)  # type: ignore[assignment]

    # --- Tier 2 (conditional) ---
    should_t2, reason_t2 = _should_escalate_to_tier_2(
        all_signals, keywords, signal_ambiguity_score=None
    )
    if should_t2:
        budget_remaining = max_budget_usd - (current_total_cost + cost_incurred)
        if budget_remaining < _TIER_2_COST_PER_CALL:
            # Budget insufficient for Tier 2 → mark FAILED (spec §5.2)
            cs["status"] = PipelineStatus.FAILED  # type: ignore[index]
            cs["errors"] = list(cs.get("errors", [])) + [  # type: ignore[index]
                CompanyError(
                    stage="signal_ingestion_tier2",
                    error_type="budget_exceeded",
                    message=f"Tier 2 required ({reason_t2}) but session budget exhausted.",
                    recoverable=False,
                )
            ]
        else:
            escalation_reasons.append(
                f"tier_2: {reason_t2} (tier_1_signals={len(tier_1_signals)})"
            )
            try:
                tier_2_signals = await run_tier_2(company_name, tavily_client)
                all_signals.extend(tier_2_signals)
                cost_incurred += _TIER_2_COST_PER_CALL
                tier_2_calls = 1
                escalation_reasons[-1] += f" tier_2_signals={len(tier_2_signals)}"
            except Exception as exc:
                cs["errors"] = list(cs.get("errors", [])) + [  # type: ignore[index]
                    CompanyError(
                        stage="signal_ingestion_tier2",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        recoverable=True,
                    )
                ]

    # --- Tier 3 (conditional) ---
    # Spec §7.2: Tier 3 triggers if BOTH:
    #   - Tier 2 composite score >= 0.75 (estimated by Tier 2 signal richness as proxy)
    #   - Enterprise budget indicators present in signals
    # Tier 3 source is configurable — if not provided, log and skip.
    # NOTE: Full composite score requires LLM severity scoring (from qualification).
    # As a proxy, we check if at least 2 Tier 2 signals were retrieved AND enterprise
    # indicators are present in the combined signal content.
    tier_2_signals_collected = [s for s in all_signals if s.get("tier") == SignalTier.TIER_2]
    tier_3_eligible = len(tier_2_signals_collected) >= 2 and _has_enterprise_indicators(all_signals)
    if tier_3_eligible:
        budget_remaining = max_budget_usd - (current_total_cost + cost_incurred)
        if budget_remaining < _TIER_3_COST_PER_CALL:
            escalation_reasons.append("tier_3: eligible but budget exhausted")
        else:
            # Tier 3 source is configurable — not yet implemented; log intent
            escalation_reasons.append(
                "tier_3: eligible (enterprise indicators detected) but no Tier 3 source configured"
            )
            # Future: call configurable Tier 3 enrichment API here
            # tier_3_calls = 1 when implemented

    # Build updated cost metadata
    updated_cost = CostMetadata(
        tier_1_calls=tier_1_calls,
        tier_2_calls=tier_2_calls,
        tier_3_calls=tier_3_calls,
        llm_tokens_used=0,
        estimated_cost_usd=cost_incurred,
        tier_escalation_reasons=escalation_reasons,
    )

    cs["raw_signals"] = all_signals  # type: ignore[index]
    cs["cost_metadata"] = updated_cost  # type: ignore[index]
    # Preserve FAILED status if budget exceeded during tier escalation
    if cs.get("status") != PipelineStatus.FAILED:  # type: ignore[index]
        cs["status"] = PipelineStatus.RUNNING  # type: ignore[index]
        cs["current_stage"] = "signal_qualification"  # type: ignore[index]

    return cs, cost_incurred  # type: ignore[return-value]

"""Signal Qualification Agent — deterministic + LLM scoring (spec §5.3).

Scoring model:
    composite_score = (0.4 × deterministic_score) + (0.6 × llm_severity_score)
    qualification_threshold = 0.45

Deterministic score:
    matched_keywords / total_capability_map_keywords, capped at 1.0

LLM severity score:
    Average of {"recency", "specificity", "technical_depth", "buying_intent"}
    All sub-dimensions 0.0–1.0.
    Falls back to deterministic-only if JSON parse fails (partial=True).

signal_ambiguity_score = 1 - mean(recency, specificity)
"""
from __future__ import annotations

import json
import logging
import statistics
from typing import Any

logger = logging.getLogger(__name__)

from langchain_core.messages import HumanMessage

from backend.config.capability_map import CapabilityMap
from backend.tracing import traceable
from backend.models.enums import HumanReviewReason, PipelineStatus, SignalTier
from backend.models.state import CompanyState, CostMetadata, QualifiedSignal, RawSignal

QUALIFICATION_THRESHOLD = 0.45
LLM_WEIGHT = 0.6
DET_WEIGHT = 0.4

# Cost estimate for LLM severity scoring
_LLM_COST_PER_CALL = 0.002


def compute_deterministic_score(
    signals: list[RawSignal],
    capability_map: CapabilityMap | None,
) -> float:
    """Keyword overlap score: matched_keywords / total_keywords, capped at 1.0.

    A keyword is "matched" if it appears in any signal's content (case-insensitive).
    Returns 0.0 if no capability map or no keywords.
    """
    if not capability_map:
        return 0.0
    all_kws = capability_map.all_keywords()
    if not all_kws:
        return 0.0

    combined_content = " ".join(s.get("content", "") for s in signals).lower()
    matched = sum(1 for kw in all_kws if kw.lower() in combined_content)
    return min(matched / len(all_kws), 1.0)


def _build_severity_prompt(signals: list[RawSignal]) -> str:
    """Build the LLM prompt for severity scoring."""
    from backend.utils.date import date_context_line
    excerpts = "\n".join(
        f"- [{s.get('signal_type', 'unknown')}] (published: {s.get('published_at') or 'unknown'}) {s.get('content', '')[:300]}"
        for s in signals[:5]
    )
    return f"""{date_context_line()}

You are evaluating whether signals indicate a company is actively investing in IT infrastructure or cloud technology — from the perspective of a B2B technology vendor selling to enterprise IT buyers.

Signals collected for the company:
{excerpts}

IMPORTANT: Score close to 0.0 for any signal that is:
- Retail promotions, sales events, or consumer-facing advertisements (e.g. "Save $25", "furniture sale")
- Generic company news with no IT/infrastructure relevance
- SEO or marketing pages with no technical content
- Job postings unrelated to IT, engineering, or infrastructure

Score each dimension from 0.0 to 1.0 (no commentary, just JSON):
- recency: How recent is the IT/infrastructure signal? (within 7 days=1.0, within 30 days=0.7, older=lower; retail/promo content=0.0)
- specificity: How specific to a concrete IT/infrastructure pain point? (retail promo=0.0, generic IT=0.3, specific infra role=0.8, detailed migration/modernization=1.0)
- technical_depth: Does the signal reference concrete IT concepts (cloud, infra, platform, security, DevOps)? (retail/promo=0.0)
- buying_intent: Does the signal suggest active IT investment or technology evaluation? (retail promotions=0.0, general IT hiring=0.3, active cloud migration or vendor evaluation=0.9)

Output ONLY valid JSON, nothing else:
{{"recency": <float>, "specificity": <float>, "technical_depth": <float>, "buying_intent": <float>}}"""


def parse_llm_severity_response(response_text: str) -> dict[str, float] | None:
    """Parse LLM JSON response. Returns None on parse failure."""
    text = response_text.strip()
    # Try to extract JSON from response (may have surrounding text)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
        required = {"recency", "specificity", "technical_depth", "buying_intent"}
        if not required.issubset(data.keys()):
            return None
        return {k: float(data[k]) for k in required}
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _normalized_llm_provider(llm_provider: str) -> str:
    """Canonicalise a provider string to ``"openai"`` or ``"anthropic"`` (default)."""
    p = (llm_provider or "").strip().lower()
    if p in ("openai", "gpt", "chatgpt", "open_ai"):
        return "openai"
    return "anthropic"


def _message_content_to_text(content: Any) -> str:
    """Flatten a LangChain message ``content`` (str | list of str/dict blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


async def call_llm_severity(
    signals: list[RawSignal],
    llm_provider: str,
    llm_model: str,
) -> tuple[dict[str, float] | None, int]:
    """Call LLM for severity scoring. Returns (scores_dict or None, tokens_used)."""
    if not llm_model:
        return None, 0

    route = _normalized_llm_provider(llm_provider)
    openai_id = llm_model.strip().lower()
    anthropic_id = llm_model.strip()

    try:
        if route == "openai":
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=openai_id, max_tokens=256, temperature=0)
        else:
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(model=anthropic_id, max_tokens=256, temperature=0)
    except ImportError:
        return None, 0

    prompt = _build_severity_prompt(signals)

    # 1 retry on rate limit
    for attempt in range(2):
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            meta = getattr(response, "usage_metadata", None) or {}
            tokens = int(meta.get("total_tokens", 0) or 0)
            text = _message_content_to_text(response.content)
            scores = parse_llm_severity_response(text)
            return scores, tokens
        except Exception as exc:
            if attempt == 0 and "rate_limit" in str(exc).lower():
                import asyncio

                await asyncio.sleep(2)
                continue
            return None, 0

    return None, 0


def compute_signal_ambiguity_score(severity_scores: dict[str, float]) -> float:
    """signal_ambiguity_score = 1 - mean(recency, specificity) (spec §5.3)."""
    recency = severity_scores.get("recency", 0.5)
    specificity = severity_scores.get("specificity", 0.5)
    return 1.0 - statistics.mean([recency, specificity])


def compute_composite_score(
    deterministic_score: float,
    llm_severity_score: float,
) -> float:
    """composite_score = 0.4 × det + 0.6 × llm (spec §5.3)."""
    return DET_WEIGHT * deterministic_score + LLM_WEIGHT * llm_severity_score


def get_all_keywords_matched(
    signals: list[RawSignal],
    capability_map: CapabilityMap | None,
) -> list[str]:
    """Return which capability map keywords appear in signal content."""
    if not capability_map:
        return []
    combined = " ".join(s.get("content", "") for s in signals).lower()
    return [kw for kw in capability_map.all_keywords() if kw.lower() in combined]


@traceable(name="run_signal_qualification")
async def run_signal_qualification(
    cs: CompanyState,
    capability_map: CapabilityMap | None,
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
) -> tuple[CompanyState, float]:
    """Qualify signals for one company. Returns (updated_cs, cost_incurred)."""
    company_name = cs.get("company_name", "?")
    signals = cs.get("raw_signals", [])
    cost_incurred = 0.0

    # Mark current stage at entry so frontend progress bar tracks correctly
    cs = dict(cs)  # type: ignore[assignment]
    cs["current_stage"] = "signal_qualification"  # type: ignore[index]

    logger.info("[%s] qualification start | signals=%d | budget_remaining=$%.3f",
                company_name, len(signals), max_budget_usd - current_total_cost)

    # Determine dominant tier
    tiers_used = {s.get("tier", SignalTier.TIER_1) for s in signals}
    tier_used = (
        SignalTier.TIER_2 if SignalTier.TIER_2 in tiers_used else SignalTier.TIER_1
    )

    # Deterministic score
    det_score = compute_deterministic_score(signals, capability_map)

    # LLM severity score (skip if budget exhausted or no model configured)
    llm_scores: dict[str, float] | None = None
    llm_tokens = 0
    partial = False

    if signals and current_total_cost + cost_incurred + _LLM_COST_PER_CALL <= max_budget_usd:
        llm_scores, llm_tokens = await call_llm_severity(
            signals, llm_provider, llm_model
        )
        if llm_scores is not None:
            cost_incurred += _LLM_COST_PER_CALL
        else:
            partial = True
    else:
        partial = bool(signals)  # had signals but skipped LLM

    # Compute severity + composite
    if llm_scores:
        llm_severity_score = statistics.mean(llm_scores.values())
        composite = compute_composite_score(det_score, llm_severity_score)
    else:
        llm_severity_score = 0.0
        # Fallback: use deterministic score only, weighted as if it were composite
        composite = det_score
        partial = True

    # Keywords matched
    keywords_matched = get_all_keywords_matched(signals, capability_map)

    # Build summary from first signal content
    summary = signals[0].get("content", "")[:200] if signals else "No signals collected."

    # Compute signal_ambiguity_score from LLM sub-dimensions (spec §5.3)
    ambiguity_score = (
        compute_signal_ambiguity_score(llm_scores)
        if llm_scores is not None
        else 0.5  # neutral default when LLM unavailable
    )

    qualified_signal = QualifiedSignal(
        company_id=cs["company_id"],
        summary=summary,
        signal_type=signals[0].get("signal_type", "unknown") if signals else "none",
        keywords_matched=keywords_matched,
        deterministic_score=det_score,
        llm_severity_score=llm_severity_score,
        composite_score=composite,
        tier_used=tier_used,
        raw_signals=signals,
        qualified=composite >= QUALIFICATION_THRESHOLD,
        disqualification_reason=(
            None
            if composite >= QUALIFICATION_THRESHOLD
            else f"composite_score {composite:.3f} < threshold {QUALIFICATION_THRESHOLD}"
        ),
        partial=partial,
        signal_ambiguity_score=ambiguity_score,
    )

    # Update cost metadata with LLM tokens (accumulate, not overwrite)
    old_cost = cs.get("cost_metadata", {})
    updated_cost = CostMetadata(
        tier_1_calls=old_cost.get("tier_1_calls", 0),
        tier_2_calls=old_cost.get("tier_2_calls", 0),
        tier_3_calls=old_cost.get("tier_3_calls", 0),
        llm_tokens_used=old_cost.get("llm_tokens_used", 0) + llm_tokens,
        estimated_cost_usd=old_cost.get("estimated_cost_usd", 0.0) + cost_incurred,
        tier_escalation_reasons=old_cost.get("tier_escalation_reasons", []),
    )

    updated_cs = dict(cs)  # type: ignore[assignment]
    updated_cs["qualified_signal"] = qualified_signal
    updated_cs["signal_qualified"] = qualified_signal["qualified"]
    updated_cs["cost_metadata"] = updated_cost
    qualified = qualified_signal["qualified"]
    logger.warning("[%s] qualification result | qualified=%s | composite=%.3f | det=%.3f | llm=%s",
                company_name, qualified, qualified_signal.get("composite_score", 0),
                det_score, f"{llm_severity_score:.3f}" if llm_scores else "none")
    updated_cs["status"] = (
        PipelineStatus.RUNNING if qualified else PipelineStatus.SKIPPED
    )
    updated_cs["current_stage"] = (
        "research" if qualified_signal["qualified"] else "done"
    )

    # SIGNAL_AMBIGUOUS: ambiguity_score > 0.7 without Tier 2 resolution (spec §5.5)
    if ambiguity_score > 0.7 and tier_used != SignalTier.TIER_2:
        updated_cs["human_review_required"] = True  # type: ignore[index]
        existing_reasons = list(updated_cs.get("human_review_reasons", []))  # type: ignore[call-overload]
        if HumanReviewReason.SIGNAL_AMBIGUOUS not in existing_reasons:
            existing_reasons.append(HumanReviewReason.SIGNAL_AMBIGUOUS)
        updated_cs["human_review_reasons"] = existing_reasons  # type: ignore[index]

    return updated_cs, cost_incurred  # type: ignore[return-value]

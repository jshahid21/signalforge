"""Draft Agent — outreach draft generation with confidence gate (spec §5.9).

Confidence gate:
    confidence_score < 60 → skip draft, set human_review_required = True

Persona-aware tone:
    economic_buyer  → business impact, scale, cost, risk (less technical)
    technical_buyer → architecture, tradeoffs, implementation (moderate-high depth)
    influencer      → developer pain points, tooling friction, concrete examples
    blocker         → risk mitigation, compliance, stability, rollback posture

Seller profile injection:
    seller_profile.portfolio_items → bridge vendor-agnostic solution areas to seller products
    No profile → vendor-agnostic draft + missing_seller_profile flag

Memory few-shot:
    Up to 2 most recent approved drafts injected as examples for tone consistency

Version:
    Draft.version starts at 1, increments on each regeneration call
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from backend.models.enums import HumanReviewReason, PipelineStatus
from backend.tracing import traceable
from backend.models.state import (
    CompanyError,
    CompanyState,
    Draft,
    Persona,
    SellerProfile,
    SynthesisOutput,
)

_DRAFT_CONFIDENCE_GATE = 35   # confidence < 35 → skip draft (truly no signal)
_DRAFT_LOW_CONFIDENCE = 60    # confidence < 60 → draft with hedged tone, no solution pitch
_LLM_COST = 0.005             # per draft

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore[assignment,misc]


def _make_llm(llm_provider: str, llm_model: str, temperature: float = 0.3):
    """Instantiate the correct LangChain LLM based on provider."""
    provider = (llm_provider or "").strip().lower()
    if provider in ("openai", "gpt", "chatgpt", "open_ai"):
        return ChatOpenAI(model=llm_model, max_tokens=800, temperature=temperature)
    else:
        return ChatAnthropic(model=llm_model, max_tokens=800, temperature=temperature)

_TONE_GUIDANCE: dict[str, str] = {
    "economic_buyer": (
        "Focus on business impact, operational scale, cost, and risk. "
        "Keep technical detail minimal — frame everything in terms of outcomes and ROI."
    ),
    "technical_buyer": (
        "Focus on architecture decisions, technical tradeoffs, and implementation path. "
        "Use moderate-to-high technical depth. Reference specific technologies where relevant."
    ),
    "influencer": (
        "Focus on developer pain points, tooling friction, and concrete day-to-day examples. "
        "Keep the tone practical and relatable. Reference specific technical frustrations they likely face."
    ),
    "blocker": (
        "Focus on risk mitigation, compliance posture, stability, and rollback posture. "
        "Be cautious and evidence-based. Address concerns before selling a solution."
    ),
}

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    HumanMessage = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]


def _build_seller_intelligence_section(
    seller_profile: SellerProfile,
    capability_enrichment: dict | None = None,
) -> str:
    """Build the seller intelligence section for the system prompt.

    If capability_enrichment is provided (from matched capability entries),
    use those specific items instead of the global intelligence lists for
    differentiators, sales_plays, and proof_points.

    Returns empty string if no intelligence is available.
    """
    intelligence = seller_profile.get("seller_intelligence")
    if not intelligence and not capability_enrichment:
        return ""

    parts: list[str] = []

    # Use capability-specific enrichment if available, otherwise fall back to global
    if capability_enrichment:
        differentiators = capability_enrichment.get("differentiators", [])
        sales_plays = capability_enrichment.get("sales_plays", [])
        proof_points = capability_enrichment.get("proof_points", [])
    else:
        differentiators = (intelligence or {}).get("differentiators", [])
        sales_plays = (intelligence or {}).get("sales_plays", [])
        proof_points = (intelligence or {}).get("proof_points", [])

    if differentiators:
        diff_list = "\n".join(f"  - {d}" for d in differentiators[:5])
        parts.append(f"Key differentiators:\n{diff_list}")

    if sales_plays:
        plays_list = "\n".join(
            f"  - {sp.get('play', '')} (category: {sp.get('category', 'general')})"
            for sp in sales_plays[:5]
        )
        parts.append(
            f"Sales plays (select the 1 most relevant to this prospect's signal; omit if none fit):\n{plays_list}"
        )

    if proof_points:
        pp_list = "\n".join(
            f"  - {pp.get('customer', '')}: {pp.get('summary', '')}"
            for pp in proof_points[:4]
        )
        parts.append(f"Proof points (use only if directly relevant to build credibility):\n{pp_list}")

    competitive = (intelligence or {}).get("competitive_positioning", [])
    if competitive:
        comp_list = "\n".join(f"  - {c}" for c in competitive[:3])
        parts.append(f"Competitive positioning:\n{comp_list}")

    if not parts:
        return ""

    return (
        "\n\n## Seller Intelligence\n"
        + "\n\n".join(parts)
        + "\n\nReference specific differentiators and proof points where relevant to the "
        "prospect's situation. Do not list all of them — pick the 1-2 most compelling for "
        "this specific persona."
    )


def _build_draft_system_prompt(
    seller_profile: Optional[SellerProfile],
    few_shot_examples: list,
    capability_enrichment: dict | None = None,
) -> str:
    """Build the system prompt with seller profile, intelligence, and few-shot memory examples."""
    parts: list[str] = [
        "You are writing a cold outreach email as a senior practitioner — not a salesperson. "
        "Your goal is to start a genuine conversation, not to sell anything. "
        "The email should read like a peer reaching out with a relevant observation, not a vendor pitching a product. "
        "\n\nCore rules:"
        "\n- Ground everything in the specific signals provided. Do not invent or assume context."
        "\n- Name the challenge or operational pressure the signals suggest — without claiming you have the answer."
        "\n- If solution alignment is strong, mention a relevant capability briefly (1 sentence). If it is weak or unclear, ask a question instead."
        "\n- The call to action is a short conversation to compare notes — NEVER a 'demo', 'presentation', or 'platform walkthrough'."
        "\n- 100–175 words maximum. Every sentence must earn its place."
        "\n\nForbidden phrases (do not use any of these): 'I hope this finds you well', "
        "'I came across', 'I wanted to reach out', 'I noticed', 'I'm reaching out because', "
        "'leverage', 'synergies', 'best-in-class', 'revolutionize', 'game-changing', "
        "'seamlessly', 'end-to-end solution', 'empower your team'."
    ]

    if seller_profile and seller_profile.get("company_name"):
        portfolio = ", ".join(seller_profile.get("portfolio_items", []))
        parts.append(
            f"\n\nSeller context: {seller_profile['company_name']} — {portfolio or 'capabilities not configured'}. "
            "Only reference this if there is a clear, specific connection to the inferred pain point. "
            "Do not force it."
        )

        # Inject seller intelligence if available (prefer capability-specific enrichment)
        intelligence_section = _build_seller_intelligence_section(
            seller_profile, capability_enrichment=capability_enrichment,
        )
        if intelligence_section:
            parts.append(intelligence_section)

        # Inject value metrics if available
        value_metrics = seller_profile.get("value_metrics", [])
        if value_metrics:
            metrics_list = "\n".join(f"  - {m}" for m in value_metrics[:3])
            parts.append(f"\n\nValue metrics (use when credibility is needed):\n{metrics_list}")

        # Note target vertical alignment if available
        target_verticals = seller_profile.get("target_verticals", [])
        if target_verticals:
            parts.append(f"\n\nSeller's target verticals: {', '.join(target_verticals)}")
    else:
        parts.append("\n\nNo seller profile — write in vendor-agnostic terms.")

    if few_shot_examples:
        parts.append("\n\nApproved examples (use for tone reference only — do not copy content):")
        for i, ex in enumerate(few_shot_examples[:2], 1):
            parts.append(
                f"\nExample {i}:\nSubject: {getattr(ex, 'draft_subject', '')}\n"
                f"Body: {getattr(ex, 'draft_body', '')[:400]}"
            )

    return "\n".join(parts)


def _build_draft_user_prompt(
    company_name: str,
    persona: Persona,
    synthesis: SynthesisOutput,
    core_problem: str,
    solution_areas: list[str],
    confidence_score: int = 50,
    raw_signal_excerpts: list[str] | None = None,
) -> str:
    from backend.utils.date import date_context_line
    tone = _TONE_GUIDANCE.get(persona["role_type"], _TONE_GUIDANCE["influencer"])

    high_confidence = confidence_score >= _DRAFT_LOW_CONFIDENCE
    solution_instruction = (
        f"Confidence is {confidence_score}/100 — strong enough. You may briefly reference a relevant capability "
        f"(1 sentence): {synthesis.get('solution_alignment', '')}. Lead with the pain point, not the product."
        if high_confidence else
        f"Confidence is {confidence_score}/100 — the signal-to-solution alignment is not strong enough to pitch anything. "
        f"Do NOT propose a solution or mention capabilities. Ask one genuine question about whether the inferred "
        f"challenge is on their radar."
    )

    excerpts = raw_signal_excerpts or []
    signals_block = "\n".join(f"  • {s[:200]}" for s in excerpts[:4]) if excerpts else "  • Limited signal data — be appropriately hedged"

    return f"""{date_context_line()}

Target: {persona['title']} at {company_name}
Persona type: {persona['role_type']}
Tone: {tone}

Signals observed (ground the email in these — do not invent context):
{signals_block}

Inferred challenge: {synthesis.get('core_pain_point', core_problem)}
Technical context: {synthesis.get('technical_context', '')}
Why this persona specifically: {synthesis.get('persona_targeting', '')}
Risk if unaddressed: {synthesis.get('risk_if_ignored', '')}

{solution_instruction}

Structure:
1. One sentence stating what the signals suggest is happening at {company_name} — specific, not generic
2. One or two sentences on the operational or technical pressure this creates — without assuming you know their situation
3. {"One sentence on a relevant capability or what you've seen work at similar companies" if high_confidence else "One direct question: is this challenge actually on their radar?"}
4. One sentence proposing a 15-minute call to compare notes — not a demo

Output ONLY valid JSON:
{{
  "subject": "<8-12 words, specific to the observed signal, zero hype>",
  "body": "<100-175 words, no clichés, grounded in the signals above>"
}}"""


def _parse_draft_response(text: str) -> dict | None:
    """Extract JSON draft from LLM response."""
    import json
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
        if "subject" not in data or "body" not in data:
            return None
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


async def run_draft(
    cs: CompanyState,
    persona: Persona,
    seller_profile: Optional[SellerProfile],
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
    few_shot_examples: list | None = None,
    existing_draft: Optional[Draft] = None,
    capability_enrichment: dict | None = None,
) -> tuple[Optional[Draft], float]:
    """Generate or regenerate a draft for a single (company, persona) pair.

    Returns (Draft or None, cost_incurred).
    None is returned when the confidence gate blocks draft generation.
    """
    company_name = cs["company_name"]
    solution_mapping = cs.get("solution_mapping")
    confidence_score = solution_mapping["confidence_score"] if solution_mapping else 0
    solution_areas = solution_mapping["solution_areas"] if solution_mapping else []
    core_problem = solution_mapping["core_problem"] if solution_mapping else ""

    # Confidence gate (spec §5.9)
    override_requested = cs.get("override_requested", False)
    if confidence_score < _DRAFT_CONFIDENCE_GATE and not override_requested:
        return None, 0.0

    # Budget check
    if current_total_cost >= max_budget_usd:
        return None, 0.0

    persona_id = persona["persona_id"]
    synthesis = cs.get("synthesis_outputs", {}).get(persona_id)
    if synthesis is None:
        return None, 0.0

    # Compute version
    version = 1
    if existing_draft is not None:
        version = existing_draft.get("version", 1) + 1

    if not llm_model or HumanMessage is None:
        # Fallback draft (no LLM)
        draft = Draft(
            draft_id=str(uuid.uuid4()),
            company_id=cs["company_id"],
            persona_id=persona_id,
            subject_line=f"[{company_name}] Technical outreach — draft unavailable (no LLM)",
            body="Draft generation requires a configured LLM model.",
            confidence_score=float(confidence_score),
            approved=False,
            version=version,
        )
        return draft, 0.0

    raw_signals = cs.get("qualified_signal", {}).get("raw_signals", []) if cs.get("qualified_signal") else []
    raw_signal_excerpts = [
        f"[{s.get('signal_type', '')}] {s.get('content', '')[:200]}"
        for s in raw_signals[:5]
        if s.get("content")
    ]

    system_prompt = _build_draft_system_prompt(
        seller_profile=seller_profile,
        few_shot_examples=few_shot_examples or [],
        capability_enrichment=capability_enrichment,
    )
    user_prompt = _build_draft_user_prompt(
        company_name=company_name,
        persona=persona,
        synthesis=synthesis,
        core_problem=core_problem,
        solution_areas=solution_areas,
        confidence_score=int(confidence_score),
        raw_signal_excerpts=raw_signal_excerpts,
    )

    # Attempt LLM call with 1 retry (2 total attempts); DRAFT_QUALITY if both fail
    parsed = None
    cost_incurred = 0.0
    trace_run_id: str | None = None
    for _attempt in range(2):
        try:
            llm = _make_llm(llm_provider, llm_model, temperature=0.3)
            # Generate a deterministic run_id so we can link LangSmith feedback later
            import uuid as _uuid
            attempt_run_id = str(_uuid.uuid4())
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
                config={"run_id": attempt_run_id},
            )
            attempt_parsed = _parse_draft_response(str(response.content))
            cost_incurred += _LLM_COST
            trace_run_id = attempt_run_id
            if attempt_parsed is not None:
                parsed = attempt_parsed
                break
        except Exception:
            continue

    if parsed:
        draft = Draft(
            draft_id=str(uuid.uuid4()),
            company_id=cs["company_id"],
            persona_id=persona_id,
            subject_line=str(parsed["subject"]).strip(),
            body=str(parsed["body"]).strip(),
            confidence_score=float(confidence_score),
            approved=False,
            version=version,
            run_id=trace_run_id,
        )
    else:
        # Both attempts failed — flag for human review (spec §5.5 DRAFT_QUALITY)
        cs = dict(cs)  # type: ignore[assignment]
        cs["human_review_required"] = True  # type: ignore[index]
        existing_reasons = list(cs.get("human_review_reasons", []))  # type: ignore[call-overload]
        if HumanReviewReason.DRAFT_QUALITY not in existing_reasons:
            existing_reasons.append(HumanReviewReason.DRAFT_QUALITY)
        cs["human_review_reasons"] = existing_reasons  # type: ignore[index]

        draft = Draft(
            draft_id=str(uuid.uuid4()),
            company_id=cs["company_id"],
            persona_id=persona_id,
            subject_line=f"[{company_name}] — draft generation failed",
            body="Draft generation failed after 2 attempts — manual review required.",
            confidence_score=float(confidence_score),
            approved=False,
            version=version,
            run_id=trace_run_id,
        )

    return draft, cost_incurred


def _build_capability_enrichment(
    matched_capability_ids: list[str],
    capability_map,
) -> dict | None:
    """Merge enrichment data from all matched capability entries into a single dict."""
    if not capability_map or not matched_capability_ids:
        return None
    import logging
    logger = logging.getLogger(__name__)
    entry_by_id = {e.id: e for e in capability_map.entries}
    merged: dict = {"differentiators": [], "sales_plays": [], "proof_points": []}
    for cap_id in matched_capability_ids:
        entry = entry_by_id.get(cap_id)
        if entry is None:
            logger.warning("Stale matched_capability_id in draft: %s", cap_id)
            continue
        merged["differentiators"].extend(entry.differentiators)
        merged["sales_plays"].extend(entry.sales_plays)
        merged["proof_points"].extend(entry.proof_points)
    # Return None if no enrichment data was found
    if not any(merged.values()):
        return None
    return merged


@traceable(name="run_drafts_for_company")
async def run_drafts_for_company(
    cs: CompanyState,
    seller_profile: Optional[SellerProfile],
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
    few_shot_examples: list | None = None,
    capability_map=None,
) -> tuple[CompanyState, float]:
    """Generate drafts for all selected personas. Returns (updated_cs, cost_incurred)."""
    solution_mapping = cs.get("solution_mapping")
    confidence_score = solution_mapping["confidence_score"] if solution_mapping else 0
    override_requested = cs.get("override_requested", False)

    cs = dict(cs)  # type: ignore[assignment]

    # Hard gate: truly no signal (below _DRAFT_CONFIDENCE_GATE)
    if confidence_score < _DRAFT_CONFIDENCE_GATE and not override_requested:
        cs["human_review_required"] = True  # type: ignore[index]
        existing_reasons = list(cs.get("human_review_reasons", []))  # type: ignore[call-overload]
        if HumanReviewReason.LOW_CONFIDENCE not in existing_reasons:
            existing_reasons.append(HumanReviewReason.LOW_CONFIDENCE)
        cs["human_review_reasons"] = existing_reasons  # type: ignore[index]
        cs["current_stage"] = "done"  # type: ignore[index]
        return cs, 0.0  # type: ignore[return-value]

    # Soft gate: low-confidence drafts still generate but are marked hedged
    if confidence_score < _DRAFT_LOW_CONFIDENCE:
        cs["low_confidence_draft"] = True  # type: ignore[index]

    if override_requested and confidence_score < _DRAFT_CONFIDENCE_GATE:
        cs["drafted_under_override"] = True  # type: ignore[index]

    selected_persona_ids = cs.get("selected_personas", [])  # type: ignore[call-overload]
    all_personas = {p["persona_id"]: p for p in cs.get("generated_personas", [])}

    personas_to_draft = [
        all_personas[pid] for pid in selected_persona_ids if pid in all_personas
    ]
    if not personas_to_draft:
        # No personas selected — fall back to all generated
        personas_to_draft = list(all_personas.values())

    # Budget reservation (issue #8 bug 3): drafts run concurrently and each
    # run_draft only checks the pre-dispatch snapshot of current_total_cost, so
    # N parallel drafts could all pass the check and collectively exceed the
    # session budget. Cap the number of concurrent drafts to what the remaining
    # budget can actually afford. This may slightly under-draft (e.g. when a
    # draft hits the confidence gate and costs nothing), but it can never
    # overspend.
    budget_remaining = max_budget_usd - current_total_cost
    if _LLM_COST > 0:
        max_affordable_drafts = max(0, int(budget_remaining // _LLM_COST))
    else:
        max_affordable_drafts = len(personas_to_draft)
    if len(personas_to_draft) > max_affordable_drafts:
        personas_to_draft = personas_to_draft[:max_affordable_drafts]

    existing_drafts = dict(cs.get("drafts", {}))

    # Build capability-specific enrichment from matched capability IDs
    matched_ids = solution_mapping.get("matched_capability_ids", []) if solution_mapping else []
    cap_enrichment = _build_capability_enrichment(matched_ids, capability_map)

    draft_tasks = [
        run_draft(
            cs=cs,  # type: ignore[arg-type]
            persona=persona,
            seller_profile=seller_profile,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_total_cost,
            max_budget_usd=max_budget_usd,
            few_shot_examples=few_shot_examples,
            existing_draft=existing_drafts.get(persona["persona_id"]),
            capability_enrichment=cap_enrichment,
        )
        for persona in personas_to_draft
    ]
    results = await asyncio.gather(*draft_tasks, return_exceptions=True)

    drafts = dict(existing_drafts)
    total_cost = 0.0
    for persona, result in zip(personas_to_draft, results):
        if isinstance(result, Exception):
            continue
        draft, cost = result
        if draft is not None:
            drafts[persona["persona_id"]] = draft
        total_cost += cost

    cs["drafts"] = drafts  # type: ignore[index]
    cs["current_stage"] = "done"  # type: ignore[index]

    return cs, total_cost  # type: ignore[return-value]

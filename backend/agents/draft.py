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

import uuid
from typing import Optional

from backend.models.enums import HumanReviewReason, PipelineStatus
from backend.models.state import (
    CompanyError,
    CompanyState,
    Draft,
    Persona,
    SellerProfile,
    SynthesisOutput,
)

_DRAFT_CONFIDENCE_GATE = 60   # confidence < 60 → skip draft
_LLM_COST = 0.005             # per draft

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
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]
    HumanMessage = None  # type: ignore[assignment]
    SystemMessage = None  # type: ignore[assignment]


def _build_draft_system_prompt(
    seller_profile: Optional[SellerProfile],
    few_shot_examples: list,
) -> str:
    """Build the system prompt with seller profile and few-shot memory examples."""
    parts: list[str] = [
        "You are a senior solutions architect writing a B2B outreach email. "
        "Your tone is technically credible and direct — not promotional or generic. "
        "Structure: Problem → technical context → solution alignment → call to action. "
        "AVOID these phrases: 'I came across your company', 'I hope this finds you well', "
        "'I wanted to reach out', 'I noticed', or any similar opener."
    ]

    if seller_profile and seller_profile.get("company_name"):
        portfolio = ", ".join(seller_profile.get("portfolio_items", []))
        parts.append(
            f"\nThe seller is from {seller_profile['company_name']}. "
            f"Products/services: {portfolio or 'not configured'}. "
            "Frame the solution alignment in terms of these specific products."
        )
    else:
        parts.append(
            "\nNo seller profile configured — write in vendor-agnostic terms."
        )

    if few_shot_examples:
        parts.append("\n\nApproved examples to guide your tone and quality:")
        for i, ex in enumerate(few_shot_examples[:2], 1):
            parts.append(
                f"\nExample {i}:\n"
                f"Subject: {getattr(ex, 'draft_subject', '')}\n"
                f"Body: {getattr(ex, 'draft_body', '')[:400]}"
            )

    return "\n".join(parts)


def _build_draft_user_prompt(
    company_name: str,
    persona: Persona,
    synthesis: SynthesisOutput,
    core_problem: str,
    solution_areas: list[str],
) -> str:
    tone = _TONE_GUIDANCE.get(persona["role_type"], _TONE_GUIDANCE["influencer"])
    areas_text = ", ".join(solution_areas) if solution_areas else "technology modernization"

    return f"""Write an outreach email for: {company_name}
Target persona: {persona['title']} ({persona['role_type']})

Tone guidance: {tone}

Context:
- Core pain point: {synthesis['core_pain_point']}
- Technical context: {synthesis['technical_context']}
- Solution alignment: {synthesis['solution_alignment']}
- Why this persona cares: {synthesis['buyer_relevance']}
- Value hypothesis: {synthesis['value_hypothesis']}
- Risk if ignored: {synthesis['risk_if_ignored']}
- Solution areas: {areas_text}

Output ONLY valid JSON:
{{
  "subject": "<Subject line — must reference a specific signal or technical fact>",
  "body": "<Full email body — 150-250 words — no generic openers>"
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

    if not llm_model or ChatAnthropic is None:
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

    system_prompt = _build_draft_system_prompt(
        seller_profile=seller_profile,
        few_shot_examples=few_shot_examples or [],
    )
    user_prompt = _build_draft_user_prompt(
        company_name=company_name,
        persona=persona,
        synthesis=synthesis,
        core_problem=core_problem,
        solution_areas=solution_areas,
    )

    try:
        llm = ChatAnthropic(model=llm_model, max_tokens=800, temperature=0.3)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        parsed = _parse_draft_response(str(response.content))
        cost_incurred = _LLM_COST
    except Exception:
        parsed = None
        cost_incurred = 0.0

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
        )
    else:
        draft = Draft(
            draft_id=str(uuid.uuid4()),
            company_id=cs["company_id"],
            persona_id=persona_id,
            subject_line=f"[{company_name}] — draft parse failed",
            body="Draft generation failed — LLM response could not be parsed.",
            confidence_score=float(confidence_score),
            approved=False,
            version=version,
        )

    return draft, cost_incurred


async def run_drafts_for_company(
    cs: CompanyState,
    seller_profile: Optional[SellerProfile],
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
    few_shot_examples: list | None = None,
) -> tuple[CompanyState, float]:
    """Generate drafts for all selected personas. Returns (updated_cs, cost_incurred)."""
    solution_mapping = cs.get("solution_mapping")
    confidence_score = solution_mapping["confidence_score"] if solution_mapping else 0
    override_requested = cs.get("override_requested", False)

    cs = dict(cs)  # type: ignore[assignment]

    # Confidence gate check for the whole company (spec §5.9)
    if confidence_score < _DRAFT_CONFIDENCE_GATE and not override_requested:
        cs["human_review_required"] = True  # type: ignore[index]
        existing_reasons = list(cs.get("human_review_reasons", []))  # type: ignore[call-overload]
        if HumanReviewReason.LOW_CONFIDENCE not in existing_reasons:
            existing_reasons.append(HumanReviewReason.LOW_CONFIDENCE)
        cs["human_review_reasons"] = existing_reasons  # type: ignore[index]
        cs["current_stage"] = "done"  # type: ignore[index]
        return cs, 0.0  # type: ignore[return-value]

    # If override requested, tag it
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

    drafts = dict(cs.get("drafts", {}))
    total_cost = 0.0

    for persona in personas_to_draft:
        existing = drafts.get(persona["persona_id"])
        draft, cost = await run_draft(
            cs=cs,  # type: ignore[arg-type]
            persona=persona,
            seller_profile=seller_profile,
            llm_provider=llm_provider,
            llm_model=llm_model,
            current_total_cost=current_total_cost + total_cost,
            max_budget_usd=max_budget_usd,
            few_shot_examples=few_shot_examples,
            existing_draft=existing,
        )
        if draft is not None:
            drafts[persona["persona_id"]] = draft
        total_cost += cost

    cs["drafts"] = drafts  # type: ignore[index]
    cs["current_stage"] = "done"  # type: ignore[index]

    return cs, total_cost  # type: ignore[return-value]

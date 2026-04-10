"""Synthesis Agent — structured insight generation per (company, persona) pair (spec §5.8).

Produces all 7 SynthesisOutput fields:
    core_pain_point, technical_context, solution_alignment,
    persona_targeting, buyer_relevance, value_hypothesis, risk_if_ignored

Runs in parallel across all selected personas via asyncio.gather().
"""
from __future__ import annotations

import asyncio
import json

from backend.models.enums import PipelineStatus
from backend.models.state import (
    CompanyError,
    CompanyState,
    Persona,
    QualifiedSignal,
    ResearchResult,
    SolutionMappingOutput,
    SynthesisOutput,
)

_LLM_COST = 0.004  # per (company, persona) pair

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    HumanMessage = None  # type: ignore[assignment]


def _make_llm(llm_provider: str, llm_model: str):
    """Instantiate the correct LangChain LLM based on provider."""
    provider = (llm_provider or "").strip().lower()
    if provider in ("openai", "gpt", "chatgpt", "open_ai"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=llm_model, max_tokens=800, temperature=0)
    else:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=llm_model, max_tokens=800, temperature=0)


def _build_synthesis_prompt(
    company_name: str,
    signal_summary: str,
    research_context: str,
    solution_areas: list[str],
    core_problem: str,
    persona_title: str,
    role_type: str,
    targeting_reason: str,
) -> str:
    from backend.utils.date import date_context_line
    areas_text = ", ".join(solution_areas) if solution_areas else "general technology modernization"
    return f"""{date_context_line()}

You are a senior solutions architect synthesizing intelligence for B2B outreach.

Company: {company_name}
Signal summary: {signal_summary}
Research context: {research_context}
Core problem identified: {core_problem}
Solution areas: {areas_text}

Target persona: {persona_title} ({role_type})
Reason for targeting: {targeting_reason}

Generate a structured insight object with these exact fields. Be specific and grounded in the signal — no generic filler.

Output ONLY valid JSON:
{{
  "core_pain_point": "<Specific technical pain this company is experiencing — 1 sentence, reference the actual signal>",
  "technical_context": "<What is known about their tech stack / architecture decisions — based only on signal and research>",
  "solution_alignment": "<Which capability areas apply and why — 1-2 sentences connecting solution areas to the pain>",
  "persona_targeting": "<Why {persona_title} specifically cares about this problem — role-specific, not generic>",
  "buyer_relevance": "<Why this persona would care — both business and technical angle combined — 1-2 sentences>",
  "value_hypothesis": "<The outcome this persona is likely optimizing for — specific and measurable where possible>",
  "risk_if_ignored": "<What happens if they don't solve this — urgency without manufactured fear — 1 sentence>"
}}"""


def _parse_synthesis_response(text: str) -> dict | None:
    """Extract JSON from LLM synthesis response."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
        required = {
            "core_pain_point", "technical_context", "solution_alignment",
            "persona_targeting", "buyer_relevance", "value_hypothesis", "risk_if_ignored",
        }
        if not required.issubset(data.keys()):
            return None
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _make_fallback_synthesis(
    company_name: str,
    core_problem: str,
    persona_title: str,
) -> SynthesisOutput:
    """Return a minimal synthesis when LLM is unavailable."""
    return SynthesisOutput(
        core_pain_point=f"{company_name} is experiencing: {core_problem}",
        technical_context="Technical context unavailable — LLM not configured.",
        solution_alignment="Solution alignment unavailable — LLM not configured.",
        persona_targeting=f"{persona_title} is targeted based on signal type.",
        buyer_relevance="Buyer relevance unavailable — LLM not configured.",
        value_hypothesis="Value hypothesis unavailable — LLM not configured.",
        risk_if_ignored="Risk analysis unavailable — LLM not configured.",
    )


async def _synthesize_for_persona(
    company_name: str,
    signal_summary: str,
    research_context: str,
    solution_areas: list[str],
    core_problem: str,
    persona: Persona,
    llm_provider: str,
    llm_model: str,
) -> SynthesisOutput:
    """Generate SynthesisOutput for a single persona. Graceful on LLM failure."""
    if not llm_model or HumanMessage is None:
        return _make_fallback_synthesis(company_name, core_problem, persona["title"])

    prompt = _build_synthesis_prompt(
        company_name=company_name,
        signal_summary=signal_summary,
        research_context=research_context,
        solution_areas=solution_areas,
        core_problem=core_problem,
        persona_title=persona["title"],
        role_type=persona["role_type"],
        targeting_reason=persona.get("targeting_reason", ""),
    )
    try:
        llm = _make_llm(llm_provider, llm_model)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        parsed = _parse_synthesis_response(str(response.content))
        if parsed:
            return SynthesisOutput(
                core_pain_point=str(parsed["core_pain_point"]).strip(),
                technical_context=str(parsed["technical_context"]).strip(),
                solution_alignment=str(parsed["solution_alignment"]).strip(),
                persona_targeting=str(parsed["persona_targeting"]).strip(),
                buyer_relevance=str(parsed["buyer_relevance"]).strip(),
                value_hypothesis=str(parsed["value_hypothesis"]).strip(),
                risk_if_ignored=str(parsed["risk_if_ignored"]).strip(),
            )
    except Exception:
        pass
    return _make_fallback_synthesis(company_name, core_problem, persona["title"])


async def run_synthesis(
    cs: CompanyState,
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
) -> tuple[CompanyState, float]:
    """Run synthesis for all selected personas in parallel.

    Returns (updated_cs, cost_incurred).
    """
    # Budget check
    if current_total_cost >= max_budget_usd:
        cs = dict(cs)  # type: ignore[assignment]
        cs["status"] = PipelineStatus.FAILED  # type: ignore[index]
        cs["errors"] = list(cs.get("errors", [])) + [  # type: ignore[index]
            CompanyError(
                stage="synthesis",
                error_type="budget_exceeded",
                message=f"Session budget ${max_budget_usd:.2f} exhausted before synthesis.",
                recoverable=False,
            )
        ]
        return cs, 0.0  # type: ignore[return-value]

    company_name = cs["company_name"]
    qualified_signal = cs.get("qualified_signal")
    research_result = cs.get("research_result")
    solution_mapping = cs.get("solution_mapping")
    selected_persona_ids = cs.get("selected_personas", [])
    all_personas = {p["persona_id"]: p for p in cs.get("generated_personas", [])}

    signal_summary = qualified_signal["summary"] if qualified_signal else ""
    core_problem = solution_mapping["core_problem"] if solution_mapping else ""
    solution_areas = solution_mapping["solution_areas"] if solution_mapping else []

    # Build research context string
    research_parts: list[str] = []
    if research_result:
        if research_result.get("company_context"):
            research_parts.append(str(research_result["company_context"]))
        if research_result.get("hiring_signals"):
            research_parts.append(str(research_result["hiring_signals"]))
        if research_result.get("tech_stack"):
            research_parts.append("Tech stack: " + ", ".join(research_result["tech_stack"]))
    research_context = " ".join(research_parts) if research_parts else "No research context."

    # Determine which personas to synthesize for
    personas_to_synthesize: list[Persona] = []
    if selected_persona_ids:
        for pid in selected_persona_ids:
            if pid in all_personas:
                personas_to_synthesize.append(all_personas[pid])
    else:
        # Fallback: use all generated personas if none selected yet
        personas_to_synthesize = list(all_personas.values())

    if not personas_to_synthesize:
        return cs, 0.0  # type: ignore[return-value]

    # Run synthesis in parallel for all personas
    synthesis_tasks = [
        _synthesize_for_persona(
            company_name=company_name,
            signal_summary=signal_summary,
            research_context=research_context,
            solution_areas=solution_areas,
            core_problem=core_problem,
            persona=persona,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        for persona in personas_to_synthesize
    ]
    results = await asyncio.gather(*synthesis_tasks, return_exceptions=True)

    synthesis_outputs = dict(cs.get("synthesis_outputs", {}))
    successful_calls = 0
    for persona, result in zip(personas_to_synthesize, results):
        if isinstance(result, Exception):
            synthesis_outputs[persona["persona_id"]] = _make_fallback_synthesis(
                company_name, core_problem, persona["title"]
            )
        else:
            synthesis_outputs[persona["persona_id"]] = result
            successful_calls += 1

    cost_incurred = _LLM_COST * max(successful_calls, 1) if llm_model else 0.0

    cs = dict(cs)  # type: ignore[assignment]
    cs["synthesis_outputs"] = synthesis_outputs  # type: ignore[index]
    cs["current_stage"] = "draft"  # type: ignore[index]

    return cs, cost_incurred  # type: ignore[return-value]

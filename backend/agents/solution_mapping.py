"""Solution Mapping Agent — LLM-first mapping to vendor-agnostic solution areas (spec §5.5, §8).

Scoring:
    confidence_score: 0–100 integer
    confidence < 50  → human_review_required = True
    confidence < 60  → Draft Agent will skip (enforced in Draft Agent)

Output constraint: solution_areas must NEVER contain vendor product names.
Novel areas (outside capability map) are noted in reasoning as "(inferred)".
"""
from __future__ import annotations

import json

from backend.config.capability_map import CapabilityMap
from backend.models.enums import HumanReviewReason
from backend.models.state import CompanyState, QualifiedSignal, ResearchResult, SolutionMappingOutput

_LLM_COST = 0.004

try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]
    HumanMessage = None  # type: ignore[assignment]

_VENDOR_NAME_BLOCKLIST = [
    "snowflake", "databricks", "aws", "amazon", "gcp", "google cloud", "azure", "microsoft",
    "confluent", "mongodb", "elastic", "datadog", "splunk", "newrelic", "grafana labs",
    "hashicorp", "terraform", "kubernetes" , "docker", "red hat", "cloudera", "palantir",
    "tableau", "looker", "dbt labs", "airbyte", "fivetran", "apache spark", "apache kafka",
]


def _build_solution_mapping_prompt(
    company_name: str,
    signal_summary: str,
    research_context: str,
    capability_map_text: str,
) -> str:
    return f"""You are a senior solutions architect mapping a B2B sales signal to vendor-agnostic solution areas.

Company: {company_name}
Signal: {signal_summary}
Research context: {research_context}

Capability Map (use as a semantic scaffold — you may also generate novel solution areas not in the map):
{capability_map_text}

Instructions:
1. Identify the core technical problem this company is trying to solve.
2. Select 2–3 solution areas that best match. Prefer capability map entries if they fit well.
   If no map entry fits, generate a novel solution area (mark it as "(inferred)" in the reasoning).
3. Assign a confidence score 0–100 based on signal specificity and how well the solution areas match.
4. NEVER include vendor product names in solution_areas (e.g., no "Snowflake", "Databricks", "AWS Glue").
   Always describe in vendor-agnostic terms (e.g., "Columnar storage optimization", "Stream processing").

Output ONLY valid JSON, no commentary:
{{
  "core_problem": "<1–2 sentences describing the core technical problem>",
  "solution_areas": ["<area 1>", "<area 2>", "<area 3 (optional)>"],
  "confidence_score": <integer 0–100>,
  "reasoning": "<explanation of why these areas match; note any inferred areas with (inferred)>"
}}"""


def _capability_map_to_text(capability_map: CapabilityMap | None) -> str:
    if not capability_map:
        return "(No capability map configured — generate solution areas from first principles.)"
    lines = []
    for entry in capability_map.entries:
        signals_text = ", ".join(entry.problem_signals[:5]) if entry.problem_signals else "N/A"
        areas_text = ", ".join(entry.solution_areas[:3]) if entry.solution_areas else "N/A"
        lines.append(f"- [{entry.label}] signals: {signals_text} | areas: {areas_text}")
    return "\n".join(lines) if lines else "(Empty capability map.)"


def _parse_solution_mapping_response(text: str) -> dict | None:
    """Extract JSON from LLM response. Returns None on failure."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
        required = {"core_problem", "solution_areas", "confidence_score", "reasoning"}
        if not required.issubset(data.keys()):
            return None
        if not isinstance(data["solution_areas"], list):
            return None
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _contains_vendor_name(area: str) -> bool:
    """Return True if a solution area contains a known vendor product name."""
    area_lower = area.lower()
    return any(vendor in area_lower for vendor in _VENDOR_NAME_BLOCKLIST)


def _sanitize_solution_areas(areas: list) -> list[str]:
    """Remove any solution areas that contain vendor names and normalize to strings."""
    return [str(a) for a in areas if isinstance(a, str) and not _contains_vendor_name(a)]


async def run_solution_mapping(
    cs: CompanyState,
    capability_map: CapabilityMap | None,
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
) -> tuple[CompanyState, float]:
    """Map qualified signal to vendor-agnostic solution areas.

    Returns (updated_cs, cost_incurred).
    """
    company_name = cs["company_name"]
    qualified_signal = cs.get("qualified_signal")
    research_result = cs.get("research_result")

    signal_summary = qualified_signal["summary"] if qualified_signal else "No signal available."
    research_context = ""
    if research_result:
        parts = []
        if research_result.get("company_context"):
            parts.append(research_result["company_context"])
        if research_result.get("hiring_signals"):
            parts.append(research_result["hiring_signals"])
        if research_result.get("tech_stack"):
            parts.append("Tech stack: " + ", ".join(research_result["tech_stack"]))
        research_context = " ".join(parts) if parts else "No research context available."

    capability_map_text = _capability_map_to_text(capability_map)
    cost_incurred = 0.0

    # Default fallback (no LLM or budget exhausted)
    fallback_mapping = SolutionMappingOutput(
        core_problem="Unable to determine — LLM not configured or budget exceeded.",
        solution_areas=[],
        confidence_score=0,
        reasoning="LLM unavailable.",
    )

    budget_remaining = max_budget_usd - current_total_cost
    if not llm_model or budget_remaining < _LLM_COST or ChatAnthropic is None:
        solution_mapping = fallback_mapping
    else:
        prompt = _build_solution_mapping_prompt(
            company_name=company_name,
            signal_summary=signal_summary,
            research_context=research_context,
            capability_map_text=capability_map_text,
        )
        try:
            llm = ChatAnthropic(model=llm_model, max_tokens=600, temperature=0)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            parsed = _parse_solution_mapping_response(str(response.content))
            cost_incurred = _LLM_COST

            if parsed:
                sanitized_areas = _sanitize_solution_areas(parsed.get("solution_areas", []))
                confidence = int(parsed.get("confidence_score", 0))
                confidence = max(0, min(100, confidence))
                solution_mapping = SolutionMappingOutput(
                    core_problem=str(parsed.get("core_problem", "")).strip(),
                    solution_areas=sanitized_areas,
                    confidence_score=confidence,
                    reasoning=str(parsed.get("reasoning", "")).strip(),
                )
            else:
                solution_mapping = fallback_mapping
        except Exception:
            solution_mapping = fallback_mapping

    cs = dict(cs)  # type: ignore[assignment]
    cs["solution_mapping"] = solution_mapping  # type: ignore[index]
    cs["current_stage"] = "persona_generation"  # type: ignore[index]

    # Confidence < 50 → flag for human review
    if solution_mapping["confidence_score"] < 50:
        cs["human_review_required"] = True  # type: ignore[index]
        existing_reasons = list(cs.get("human_review_reasons", []))  # type: ignore[call-overload]
        if HumanReviewReason.LOW_CONFIDENCE not in existing_reasons:
            existing_reasons.append(HumanReviewReason.LOW_CONFIDENCE)
        cs["human_review_reasons"] = existing_reasons  # type: ignore[index]

    return cs, cost_incurred  # type: ignore[return-value]

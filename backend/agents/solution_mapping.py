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
from backend.tracing import traceable
from backend.models.enums import HumanReviewReason
from backend.models.state import CompanyState, QualifiedSignal, ResearchResult, SolutionMappingOutput

_LLM_COST = 0.004

try:
    from langchain_core.messages import HumanMessage
except ImportError:
    HumanMessage = None  # type: ignore[assignment]

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore[assignment,misc]


def _make_llm(llm_provider: str, llm_model: str):
    provider = (llm_provider or "").strip().lower()
    if provider in ("openai", "gpt", "chatgpt", "open_ai"):
        return ChatOpenAI(model=llm_model, max_tokens=600, temperature=0)
    else:
        return ChatAnthropic(model=llm_model, max_tokens=600, temperature=0)

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
    from backend.utils.date import date_context_line
    return f"""{date_context_line()}

You are a senior solutions architect mapping a B2B sales signal to vendor-agnostic solution areas.

Company: {company_name}
Signal: {signal_summary}
Research context: {research_context}

Capability Map (use as a semantic scaffold — you may also generate novel solution areas not in the map):
{capability_map_text}

Instructions:
1. Identify the core technical problem this company is trying to solve.
   The core_problem MUST be specific to this company. It MUST include:
   - The company name
   - At least one concrete detail from the signal or research context (e.g., named technologies,
     specific scale indicators, team sizes, business metrics, or concrete business outcomes)
   - What specifically they are trying to achieve or struggling with
   Do NOT write a generic problem statement that could apply to any company.
2. Select 2–3 solution areas that best match. Prefer capability map entries if they fit well.
   If no map entry fits, generate a novel solution area (mark it as "(inferred)" in the reasoning).
3. Assign a confidence score 0–100 based on signal specificity and how well the solution areas match.
4. NEVER include vendor product names in solution_areas (e.g., no "Snowflake", "Databricks", "AWS Glue").
   Always describe in vendor-agnostic terms (e.g., "Columnar storage optimization", "Stream processing").

Examples of BAD vs GOOD core_problem:
- BAD: "Scaling ML infrastructure to meet growing demands."
- GOOD: "{company_name} is scaling its Kubernetes-based ML platform to support real-time fraud detection, as indicated by active hiring for ML platform and infrastructure engineers."
- BAD: "Modernizing data infrastructure for better analytics."
- GOOD: "{company_name} is migrating from batch ETL to stream processing to reduce reporting latency from hours to minutes, driven by its growth in transaction volume."

5. Return the IDs of capability map entries whose solution areas best match (from the [id: ...] tags above).
   If no capability map is configured, return an empty list.

Output ONLY valid JSON, no commentary:
{{
  "core_problem": "<1–2 sentences with company-specific details as described above>",
  "solution_areas": ["<area 1>", "<area 2>", "<area 3 (optional)>"],
  "inferred_areas": ["<list only areas NOT present in the capability map above; use [] if all areas are from the map>"],
  "matched_capability_ids": ["<id of matched capability entry>"],
  "confidence_score": <integer 0–100>,
  "reasoning": "<explanation of why these areas match>"
}}"""


def _capability_map_to_text(capability_map: CapabilityMap | None) -> str:
    """Render the capability map as one line per entry for embedding in the LLM prompt.

    Format per entry: ``- [id: <id>] <label> | signals: a, b, c | areas: x, y``
    (signals truncated to 5, areas to 3; falls back to a placeholder when the map is empty/None).
    """
    if not capability_map:
        return "(No capability map configured — generate solution areas from first principles.)"
    lines = []
    for entry in capability_map.entries:
        signals_text = ", ".join(entry.problem_signals[:5]) if entry.problem_signals else "N/A"
        areas_text = ", ".join(entry.solution_areas[:3]) if entry.solution_areas else "N/A"
        lines.append(f"- [id: {entry.id}] {entry.label} | signals: {signals_text} | areas: {areas_text}")
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
        # inferred_areas is optional in LLM output; default to []
        if "inferred_areas" not in data:
            data["inferred_areas"] = []
        # matched_capability_ids is optional; default to []
        if "matched_capability_ids" not in data:
            data["matched_capability_ids"] = []
        elif not isinstance(data["matched_capability_ids"], list):
            data["matched_capability_ids"] = []
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


@traceable(name="run_solution_mapping")
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

    # Mark current stage at entry so frontend progress bar tracks correctly
    cs = dict(cs)  # type: ignore[assignment]
    cs["current_stage"] = "solution_mapping"  # type: ignore[index]

    qualified_signal = cs.get("qualified_signal")
    research_result = cs.get("research_result")

    signal_summary = qualified_signal["summary"] if qualified_signal else "No signal available."
    research_context = ""
    if research_result:
        parts = []
        if research_result.get("company_context"):
            parts.append("Company context: " + research_result["company_context"])
        if research_result.get("hiring_signals"):
            parts.append("Hiring signals: " + research_result["hiring_signals"])
        if research_result.get("tech_stack"):
            parts.append("Tech stack: " + ", ".join(research_result["tech_stack"]))
        research_context = "\n".join(parts) if parts else "No research context available."
    else:
        research_context = "No research context available."

    capability_map_text = _capability_map_to_text(capability_map)
    cost_incurred = 0.0

    # Default fallback (no LLM or budget exhausted)
    fallback_mapping = SolutionMappingOutput(
        core_problem="Unable to determine — LLM not configured or budget exceeded.",
        solution_areas=[],
        inferred_areas=[],
        matched_capability_ids=[],
        confidence_score=0,
        reasoning="LLM unavailable.",
    )

    budget_remaining = max_budget_usd - current_total_cost
    if not llm_model or budget_remaining < _LLM_COST or HumanMessage is None:
        solution_mapping = fallback_mapping
    else:
        prompt = _build_solution_mapping_prompt(
            company_name=company_name,
            signal_summary=signal_summary,
            research_context=research_context,
            capability_map_text=capability_map_text,
        )
        try:
            llm = _make_llm(llm_provider, llm_model)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            parsed = _parse_solution_mapping_response(str(response.content))
            cost_incurred = _LLM_COST

            if parsed:
                sanitized_areas = _sanitize_solution_areas(parsed.get("solution_areas", []))
                raw_inferred = parsed.get("inferred_areas", [])
                inferred_areas = [str(a) for a in raw_inferred if isinstance(a, str)]
                confidence = int(parsed.get("confidence_score", 0))
                confidence = max(0, min(100, confidence))
                matched_ids = [
                    str(mid) for mid in parsed.get("matched_capability_ids", [])
                    if isinstance(mid, str)
                ]
                solution_mapping = SolutionMappingOutput(
                    core_problem=str(parsed.get("core_problem", "")).strip(),
                    solution_areas=sanitized_areas,
                    inferred_areas=inferred_areas,
                    matched_capability_ids=matched_ids,
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

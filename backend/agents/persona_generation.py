"""Persona Generation Agent — balanced buying group with signal→persona bias (spec §5.6).

Bias rules (applied deterministically from signal type):
    Hiring (engineering roles)  → Technical Buyer + 1–2 Influencers
    Infra scaling               → Technical Buyer + Economic Buyer
    Cost optimization           → Economic Buyer + FinOps Influencer
    ML/AI signals               → Head of AI (economic) + ML Platform Lead (technical) + ML Engineer (influencer)
    Security/compliance         → Blocker + Economic Buyer
    Default                     → Technical Buyer + Economic Buyer + Influencer

Recommended outreach sequence:
    - Start with influencer or technical_buyer for technical signals (hiring/infra/ML)
    - Start with economic_buyer for strategic signals (funding, cost optimization)
    - Avoid leading with exec unless signal is strategic
"""
from __future__ import annotations

import uuid
from typing import Literal

from backend.models.enums import HumanReviewReason
from backend.models.state import CompanyState, Persona, SolutionMappingOutput

_LLM_COST = 0.003

# Signal type classification keywords
_ML_KEYWORDS = {"ml", "machine learning", "ai", "artificial intelligence", "llm", "gpu",
                 "tensorflow", "pytorch", "deep learning", "neural", "mlops", "ml platform",
                 "head of ai", "ml engineer", "ml infra", "data science"}
_INFRA_KEYWORDS = {"kubernetes", "k8s", "platform engineering", "sre", "site reliability",
                   "cloud infrastructure", "infrastructure", "devops", "platform team",
                   "distributed systems", "reliability", "scalability", "multi-region"}
_COST_KEYWORDS = {"finops", "cost optimization", "cost reduction", "cloud spend", "budget",
                  "savings", "rightsizing", "cost efficiency", "cloud cost"}
_SECURITY_KEYWORDS = {"security", "compliance", "sox", "gdpr", "hipaa", "pci", "audit",
                      "vulnerability", "zero trust", "devsecops", "soc2", "iso27001"}


def _classify_signal(signal_summary: str, solution_areas: list[str], signal_type: str) -> str:
    """Classify a signal into a persona bias category.

    Returns one of: "ml_ai", "infra_scaling", "cost_optimization",
                    "security_compliance", "hiring_engineering", "default"
    """
    combined = (signal_summary + " " + " ".join(solution_areas)).lower()

    if any(kw in combined for kw in _ML_KEYWORDS):
        return "ml_ai"
    if any(kw in combined for kw in _COST_KEYWORDS):
        return "cost_optimization"
    if any(kw in combined for kw in _SECURITY_KEYWORDS):
        return "security_compliance"
    if any(kw in combined for kw in _INFRA_KEYWORDS):
        return "infra_scaling"
    if signal_type == "job_posting":
        return "hiring_engineering"
    return "default"


def _make_persona(
    title: str,
    role_type: Literal["economic_buyer", "technical_buyer", "influencer", "blocker"],
    seniority_level: Literal["exec", "director", "manager", "ic"],
    targeting_reason: str,
    priority_score: float,
) -> Persona:
    return Persona(
        persona_id=str(uuid.uuid4()),
        title=title,
        targeting_reason=targeting_reason,
        role_type=role_type,
        seniority_level=seniority_level,
        priority_score=priority_score,
        is_custom=False,
        is_edited=False,
    )


def _build_personas_for_category(
    category: str,
    core_problem: str,
    solution_areas: list[str],
    company_name: str,
) -> list[Persona]:
    """Build deterministic personas for the given signal category."""
    areas_text = ", ".join(solution_areas[:3]) if solution_areas else "technology modernization"

    if category == "ml_ai":
        return [
            _make_persona(
                title="Head of AI",
                role_type="economic_buyer",
                seniority_level="exec",
                targeting_reason=(
                    f"As budget owner for AI/ML investments at {company_name}, "
                    f"owns strategic decisions around {areas_text}."
                ),
                priority_score=0.7,
            ),
            _make_persona(
                title="ML Platform Lead",
                role_type="technical_buyer",
                seniority_level="director",
                targeting_reason=(
                    f"Owns implementation of ML infrastructure. Directly responsible "
                    f"for solving {core_problem}."
                ),
                priority_score=0.9,
            ),
            _make_persona(
                title="Senior ML Engineer",
                role_type="influencer",
                seniority_level="ic",
                targeting_reason=(
                    "Day-to-day practitioner with direct pain from current tooling gaps. "
                    "Strong technical evaluator and internal champion."
                ),
                priority_score=0.8,
            ),
        ]

    if category == "infra_scaling":
        return [
            _make_persona(
                title="Head of Platform Engineering",
                role_type="technical_buyer",
                seniority_level="director",
                targeting_reason=(
                    f"Owns infrastructure strategy at {company_name}. "
                    f"Directly accountable for {areas_text}."
                ),
                priority_score=0.9,
            ),
            _make_persona(
                title="VP of Engineering",
                role_type="economic_buyer",
                seniority_level="exec",
                targeting_reason=(
                    f"Budget authority for platform investments. Cares about {areas_text} "
                    "from a team velocity and reliability standpoint."
                ),
                priority_score=0.7,
            ),
            _make_persona(
                title="Staff Site Reliability Engineer",
                role_type="influencer",
                seniority_level="ic",
                targeting_reason=(
                    "Technical evaluator with deep knowledge of operational pain points. "
                    "Influences vendor and tooling selection."
                ),
                priority_score=0.75,
            ),
        ]

    if category == "cost_optimization":
        return [
            _make_persona(
                title="VP of Engineering",
                role_type="economic_buyer",
                seniority_level="exec",
                targeting_reason=(
                    f"Budget owner for infrastructure and cloud spend at {company_name}. "
                    f"Directly motivated by {areas_text}."
                ),
                priority_score=0.9,
            ),
            _make_persona(
                title="FinOps Lead",
                role_type="influencer",
                seniority_level="manager",
                targeting_reason=(
                    "Owns cloud cost governance and optimization strategy. "
                    "Primary evaluator for cost-focused tooling."
                ),
                priority_score=0.85,
            ),
            _make_persona(
                title="Director of Cloud Infrastructure",
                role_type="technical_buyer",
                seniority_level="director",
                targeting_reason=(
                    "Owns cloud architecture decisions. Responsible for implementing "
                    "cost optimization measures across the platform."
                ),
                priority_score=0.75,
            ),
        ]

    if category == "security_compliance":
        return [
            _make_persona(
                title="VP of Engineering",
                role_type="economic_buyer",
                seniority_level="exec",
                targeting_reason=(
                    f"Accountable for compliance posture at {company_name}. "
                    "Approves security tooling investments."
                ),
                priority_score=0.8,
            ),
            _make_persona(
                title="Head of Security Engineering",
                role_type="blocker",
                seniority_level="director",
                targeting_reason=(
                    "Controls security and compliance requirements. Must be aligned "
                    "before any vendor evaluation can proceed."
                ),
                priority_score=0.9,
            ),
        ]

    if category == "hiring_engineering":
        # spec §5.6: Hiring (engineering roles) → Technical Buyer + 1–2 Influencers ONLY
        return [
            _make_persona(
                title="Head of Platform Engineering",
                role_type="technical_buyer",
                seniority_level="director",
                targeting_reason=(
                    f"Owns the technology decisions tied to {company_name}'s hiring push. "
                    f"Evaluates solutions for {areas_text}."
                ),
                priority_score=0.9,
            ),
            _make_persona(
                title="Staff Engineer",
                role_type="influencer",
                seniority_level="ic",
                targeting_reason=(
                    "Technical leader shaping architecture decisions. "
                    "Key internal evaluator for new tooling."
                ),
                priority_score=0.8,
            ),
            _make_persona(
                title="Senior Software Engineer",
                role_type="influencer",
                seniority_level="ic",
                targeting_reason=(
                    "Day-to-day practitioner experiencing the tooling pain. "
                    "Drives internal demand and word-of-mouth evaluation."
                ),
                priority_score=0.7,
            ),
        ]

    # Default: balanced buying group
    return [
        _make_persona(
            title="Director of Cloud Infrastructure",
            role_type="technical_buyer",
            seniority_level="director",
            targeting_reason=(
                f"Owns technical implementation decisions at {company_name}. "
                f"Accountable for {areas_text}."
            ),
            priority_score=0.9,
        ),
        _make_persona(
            title="VP of Engineering",
            role_type="economic_buyer",
            seniority_level="exec",
            targeting_reason=(
                "Budget authority for infrastructure and platform investments."
            ),
            priority_score=0.75,
        ),
        _make_persona(
            title="Senior Platform Engineer",
            role_type="influencer",
            seniority_level="ic",
            targeting_reason=(
                "Day-to-day practitioner. Strong technical evaluator and internal champion."
            ),
            priority_score=0.8,
        ),
    ]


def _compute_outreach_sequence(personas: list[Persona], category: str) -> list[str]:
    """Compute recommended outreach sequence (ordered persona_ids).

    Rules (spec §5.6):
    - Start with influencer or technical_buyer for technical signals (hiring/infra/ML)
    - Start with economic_buyer for strategic signals (cost_optimization)
    - Avoid leading with exec unless signal is strategic
    """
    # Sort by priority_score descending first
    sorted_personas = sorted(personas, key=lambda p: p["priority_score"], reverse=True)

    # Technical signals: technical_buyer or influencer first, then economic_buyer
    if category in ("ml_ai", "infra_scaling", "hiring_engineering"):
        # Prefer technical_buyer first, then influencer, then economic_buyer/exec last
        ordered = (
            [p for p in sorted_personas if p["role_type"] == "technical_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "influencer"]
            + [p for p in sorted_personas if p["role_type"] == "economic_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "blocker"]
        )
    elif category == "cost_optimization":
        # Economic buyer first (strategic signal)
        ordered = (
            [p for p in sorted_personas if p["role_type"] == "economic_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "influencer"]
            + [p for p in sorted_personas if p["role_type"] == "technical_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "blocker"]
        )
    elif category == "security_compliance":
        # Blocker must be aligned first
        ordered = (
            [p for p in sorted_personas if p["role_type"] == "blocker"]
            + [p for p in sorted_personas if p["role_type"] == "economic_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "technical_buyer"]
            + [p for p in sorted_personas if p["role_type"] == "influencer"]
        )
    else:
        ordered = sorted_personas

    # De-duplicate (preserve order)
    seen: set[str] = set()
    result: list[str] = []
    for p in ordered:
        if p["persona_id"] not in seen:
            seen.add(p["persona_id"])
            result.append(p["persona_id"])
    return result


async def run_persona_generation(
    cs: CompanyState,
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
) -> tuple[CompanyState, float]:
    """Generate personas for a company based on signal type and solution mapping.

    Applies deterministic bias rules; does not require LLM (LLM is optional for
    targeting_reason enrichment in future phases).

    Returns (updated_cs, cost_incurred).
    """
    company_name = cs["company_name"]
    qualified_signal = cs.get("qualified_signal")
    solution_mapping = cs.get("solution_mapping")

    signal_summary = qualified_signal["summary"] if qualified_signal else ""
    signal_type = qualified_signal["signal_type"] if qualified_signal else "unknown"
    solution_areas = solution_mapping["solution_areas"] if solution_mapping else []
    core_problem = solution_mapping["core_problem"] if solution_mapping else ""

    # Classify signal into a bias category (deterministic)
    category = _classify_signal(signal_summary, solution_areas, signal_type)

    # Build personas deterministically from the bias rules
    personas = _build_personas_for_category(
        category=category,
        core_problem=core_problem,
        solution_areas=solution_areas,
        company_name=company_name,
    )

    # Compute recommended outreach sequence
    sequence = _compute_outreach_sequence(personas, category)

    cs = dict(cs)  # type: ignore[assignment]
    cs["generated_personas"] = personas  # type: ignore[index]
    cs["recommended_outreach_sequence"] = sequence  # type: ignore[index]
    cs["current_stage"] = "awaiting_persona_selection"  # type: ignore[index]

    return cs, 0.0  # type: ignore[return-value]

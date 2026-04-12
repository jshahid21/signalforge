"""Research Agent — parallel sub-tasks for a qualified company (spec §5.4).

Sub-tasks (all run concurrently via asyncio.gather):
    1. Company context   — general market/company background (LLM)
    2. Tech stack        — explicit technology mentions only; NO inference (LLM extraction)
    3. Hiring signals    — hiring trend summary (LLM)

Each sub-task wraps in its own try/except. If any fail, partial=True is set.
"""
from __future__ import annotations

import asyncio
import json

from backend.models.enums import PipelineStatus
from backend.tracing import traceable
from backend.models.state import CompanyError, CompanyState, ResearchResult

# Approximate USD cost per LLM call (3 sub-tasks total)
_LLM_COST_PER_SUBTASK = 0.003


def _make_llm(llm_provider: str, llm_model: str, max_tokens: int = 300):
    provider = (llm_provider or "").strip().lower()
    if provider in ("openai", "gpt", "chatgpt", "open_ai"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=llm_model, max_tokens=max_tokens, temperature=0)
    else:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=llm_model, max_tokens=max_tokens, temperature=0)


async def _run_company_context(
    company_name: str,
    signal_summary: str,
    llm_provider: str,
    llm_model: str,
) -> str | None:
    """Return 2–3 sentences of company/market context from LLM."""
    if not llm_model:
        return None
    from backend.utils.date import date_context_line
    prompt = f"""{date_context_line()}

You are a B2B technology sales researcher.

Company: {company_name}
Signal summary: {signal_summary}

Provide 2–3 concise sentences of company context that would help a technical seller understand \
the company's strategic situation — growth trajectory, market position, and relevance to \
technology investment decisions. Be factual. Do not fabricate information."""
    try:
        from langchain_core.messages import HumanMessage
        llm = _make_llm(llm_provider, llm_model, max_tokens=300)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content).strip() or None
    except Exception:
        return None


async def _run_tech_stack_extraction(
    signals_content: str,
    llm_provider: str,
    llm_model: str,
) -> list[str]:
    """Extract explicitly mentioned technologies from signal text. No inference."""
    if not llm_model or not signals_content.strip():
        return []
    prompt = f"""Extract all technology names that are EXPLICITLY MENTIONED in the text below.
DO NOT infer, assume, or guess any technologies. Only include names literally present in the text.

Text:
{signals_content[:2000]}

Output ONLY a JSON array of lowercase technology names. If none are found, output [].
Example: ["kubernetes", "tensorflow", "postgres"]"""
    try:
        from langchain_core.messages import HumanMessage
        llm = _make_llm(llm_provider, llm_model, max_tokens=200)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text = str(response.content).strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        parsed = json.loads(text[start:end])
        return [str(t) for t in parsed if isinstance(t, str)]
    except Exception:
        return []


async def _run_hiring_signal_analysis(
    company_name: str,
    signals_content: str,
    llm_provider: str,
    llm_model: str,
) -> str | None:
    """Summarize hiring trends and technology investment priorities from signal content."""
    if not llm_model or not signals_content.strip():
        return None
    from backend.utils.date import date_context_line
    prompt = f"""{date_context_line()}

Analyze the hiring signals for {company_name}:

{signals_content[:2000]}

Summarize in 1–2 sentences what these hiring patterns indicate about the company's technology \
investment priorities and growth areas. Focus on patterns, not individual roles."""
    try:
        from langchain_core.messages import HumanMessage
        llm = _make_llm(llm_provider, llm_model, max_tokens=200)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return str(response.content).strip() or None
    except Exception:
        return None


_INDUSTRY_TAXONOMY = [
    "fintech", "healthcare", "e-commerce", "saas", "cybersecurity",
    "devtools", "media", "logistics", "education", "enterprise_software", "other",
]


async def _run_industry_classification(
    company_name: str,
    signal_summary: str,
    llm_provider: str,
    llm_model: str,
) -> str | None:
    """Classify the target company into a standard industry taxonomy."""
    if not llm_model:
        return None
    taxonomy_str = ", ".join(_INDUSTRY_TAXONOMY)
    prompt = f"""Classify this company into exactly one industry category.

Company: {company_name}
Signal summary: {signal_summary}

Categories: {taxonomy_str}

Output ONLY the category name (one word, lowercase). If uncertain, output "other"."""
    try:
        from langchain_core.messages import HumanMessage
        llm = _make_llm(llm_provider, llm_model, max_tokens=20)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = str(response.content).strip().lower().replace('"', "").replace("'", "")
        return result if result in _INDUSTRY_TAXONOMY else "other"
    except Exception:
        return None


@traceable(name="run_research")
async def run_research(
    cs: CompanyState,
    llm_provider: str,
    llm_model: str,
    current_total_cost: float,
    max_budget_usd: float,
) -> tuple[CompanyState, float]:
    """Run parallel research sub-tasks for a qualified company.

    Returns (updated_cs, cost_incurred).
    Graceful: continues even if individual sub-tasks fail; sets partial=True.
    """
    # Mark current stage at entry so frontend progress bar tracks correctly
    cs = dict(cs)  # type: ignore[assignment]
    cs["current_stage"] = "research"  # type: ignore[index]

    # Budget check before any LLM calls
    if current_total_cost >= max_budget_usd:
        cs = dict(cs)  # type: ignore[assignment]
        cs["status"] = PipelineStatus.FAILED  # type: ignore[index]
        cs["errors"] = list(cs.get("errors", [])) + [  # type: ignore[index]
            CompanyError(
                stage="research",
                error_type="budget_exceeded",
                message=f"Session budget ${max_budget_usd:.2f} exhausted before research.",
                recoverable=False,
            )
        ]
        return cs, 0.0  # type: ignore[return-value]

    company_name = cs["company_name"]
    qualified_signal = cs.get("qualified_signal")
    signal_summary = qualified_signal["summary"] if qualified_signal else ""

    raw_signals = cs.get("raw_signals", [])
    signals_content = " ".join(s.get("content", "") for s in raw_signals)

    # Run all 4 sub-tasks concurrently; return_exceptions captures individual failures
    results = await asyncio.gather(
        _run_company_context(company_name, signal_summary, llm_provider, llm_model),
        _run_tech_stack_extraction(signals_content, llm_provider, llm_model),
        _run_hiring_signal_analysis(company_name, signals_content, llm_provider, llm_model),
        _run_industry_classification(company_name, signal_summary, llm_provider, llm_model),
        return_exceptions=True,
    )

    company_context_raw, tech_stack_raw, hiring_signals_raw, industry_raw = results

    partial = False

    # Resolve company_context
    if isinstance(company_context_raw, Exception) or company_context_raw is None:
        company_context: str | None = None
        if isinstance(company_context_raw, Exception):
            partial = True
    else:
        company_context = company_context_raw

    # Resolve tech_stack
    if isinstance(tech_stack_raw, Exception):
        tech_stack: list[str] = []
        partial = True
    elif isinstance(tech_stack_raw, list):
        tech_stack = tech_stack_raw
    else:
        tech_stack = []

    # Resolve hiring_signals
    if isinstance(hiring_signals_raw, Exception) or hiring_signals_raw is None:
        hiring_signals: str | None = None
        if isinstance(hiring_signals_raw, Exception):
            partial = True
    else:
        hiring_signals = hiring_signals_raw

    # Resolve industry classification
    if isinstance(industry_raw, Exception) or industry_raw is None:
        industry: str | None = None
        if isinstance(industry_raw, Exception):
            partial = True
    else:
        industry = industry_raw

    # Partial if any result is missing (regardless of LLM config)
    if company_context is None or hiring_signals is None:
        partial = True

    # Estimate cost: charge for sub-tasks that had LLM configured (now 4 sub-tasks)
    cost_incurred = _LLM_COST_PER_SUBTASK * 4 if llm_model else 0.0

    research_result = ResearchResult(
        company_context=company_context,
        tech_stack=tech_stack,
        hiring_signals=hiring_signals,
        partial=partial,
    )

    cs = dict(cs)  # type: ignore[assignment]
    cs["research_result"] = research_result  # type: ignore[index]
    cs["industry"] = industry  # type: ignore[index]
    cs["current_stage"] = "solution_mapping"  # type: ignore[index]

    return cs, cost_incurred  # type: ignore[return-value]

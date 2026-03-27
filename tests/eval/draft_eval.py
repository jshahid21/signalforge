"""LLM-as-judge evaluation harness for draft quality (spec §13.4).

Usage:
    python -m tests.eval.draft_eval --fixture-results-dir /path/to/results

This module is NOT included in the standard pytest suite (requires a real LLM API key).
Run it separately to evaluate draft quality against the 10 canonical company fixtures.

Evaluation dimensions (spec §13.4):
  1. Technical credibility  — signal referenced, specific, not generic
  2. Tone adherence         — no generic phrases, matches persona role_type
  3. Solution mapping accuracy (optional, requires human labels)

Rubric design:
  Each dimension is scored 1–5 by the judge LLM.
  Scores are aggregated per dimension across all fixture companies.
  A passing threshold of >= 3.5 is required for each dimension.

Output:
  JSON report at tests/eval/results/draft_eval_<timestamp>.json
  Summary table printed to stdout.

Example invocation (requires ANTHROPIC_API_KEY env var):
    python -m tests.eval.draft_eval --fixture-results-dir tests/eval/sample_results
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Rubric
# ---------------------------------------------------------------------------

JUDGE_RUBRIC = """You are evaluating the quality of a B2B sales outreach email drafted by an AI system.

## Company Context
Company: {company_name}
Signal Summary: {signal_summary}
Persona: {persona_title} ({role_type})

## Draft to Evaluate
Subject: {subject_line}
Body:
{body}

## Scoring Rubric

Score each dimension from 1 to 5 (integers only).

### 1. Technical Credibility (specificity)
- 5: Directly references the specific signal (e.g., "noticed your ML platform hiring spike")
- 4: References a specific technical area without naming the exact signal
- 3: Mentions a relevant technical topic but stays generic
- 2: Technical topic is only vaguely present
- 1: No technical specificity — could apply to any company

### 2. Tone Adherence (persona match)
- 5: Perfectly matches the persona's role_type (economic_buyer → ROI/cost; technical_buyer → architecture; influencer → developer pain points)
- 4: Mostly appropriate tone with minor mismatches
- 3: Neutral tone — not wrong but not persona-specific
- 2: Tone mismatch — e.g., heavy ROI language for a technical buyer
- 1: Tone is clearly inappropriate for this persona

### 3. No Generic Phrases
- 5: Zero generic filler phrases ("hope this finds you well", "I wanted to reach out", etc.)
- 4: One minor generic phrase
- 3: Two generic phrases
- 2: Multiple generic phrases throughout
- 1: Draft is primarily composed of generic phrases

Output ONLY valid JSON, no commentary:
{{"technical_credibility": <int>, "tone_adherence": <int>, "no_generic_phrases": <int>, "reasoning": "<one sentence>"}}
"""

PASSING_THRESHOLD = 3.5  # Minimum average score per dimension to pass


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class DraftEvaluator:
    """LLM-as-judge for SignalForge draft quality."""

    def __init__(self, llm_model: str = "claude-sonnet-4-6") -> None:
        self.llm_model = llm_model
        self._llm = None

    def _get_llm(self) -> Any:
        """Lazy-initialize the LLM client. Requires ANTHROPIC_API_KEY."""
        if self._llm is None:
            try:
                from langchain_anthropic import ChatAnthropic
                self._llm = ChatAnthropic(model=self.llm_model, max_tokens=500, temperature=0)
            except ImportError:
                raise RuntimeError(
                    "langchain_anthropic is required for eval. "
                    "Install with: pip install langchain-anthropic"
                )
        return self._llm

    async def evaluate_draft(
        self,
        company_name: str,
        signal_summary: str,
        persona_title: str,
        role_type: str,
        subject_line: str,
        body: str,
    ) -> dict[str, Any]:
        """Score a single draft on the rubric. Returns dict with scores."""
        from langchain_core.messages import HumanMessage

        prompt = JUDGE_RUBRIC.format(
            company_name=company_name,
            signal_summary=signal_summary,
            persona_title=persona_title,
            role_type=role_type,
            subject_line=subject_line,
            body=body,
        )

        llm = self._get_llm()
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            content = str(response.content).strip()
            # Extract JSON
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                scores = json.loads(content[start:end])
            else:
                scores = {"error": "Could not parse judge response", "raw": content}
        except Exception as exc:
            scores = {"error": str(exc)}

        return {
            "company_name": company_name,
            "persona_title": persona_title,
            "role_type": role_type,
            "subject_line": subject_line,
            **scores,
        }

    async def evaluate_all(self, draft_results: list[dict]) -> dict[str, Any]:
        """Evaluate all draft results and aggregate scores.

        Args:
            draft_results: List of dicts, each with:
                - company_name, signal_summary, persona_title, role_type,
                  subject_line, body

        Returns:
            Aggregated report with per-dimension averages and pass/fail verdict.
        """
        import asyncio

        tasks = [
            self.evaluate_draft(
                company_name=r["company_name"],
                signal_summary=r.get("signal_summary", ""),
                persona_title=r.get("persona_title", ""),
                role_type=r.get("role_type", "technical_buyer"),
                subject_line=r.get("subject_line", ""),
                body=r.get("body", ""),
            )
            for r in draft_results
        ]
        individual_results = await asyncio.gather(*tasks)

        # Aggregate scores
        dims = ["technical_credibility", "tone_adherence", "no_generic_phrases"]
        dim_scores: dict[str, list[float]] = {d: [] for d in dims}

        for result in individual_results:
            for dim in dims:
                if dim in result and isinstance(result[dim], (int, float)):
                    dim_scores[dim].append(float(result[dim]))

        averages = {
            dim: (sum(scores) / len(scores) if scores else 0.0)
            for dim, scores in dim_scores.items()
        }

        passed = all(avg >= PASSING_THRESHOLD for avg in averages.values())

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "llm_model": self.llm_model,
            "num_drafts_evaluated": len(individual_results),
            "dimension_averages": averages,
            "passing_threshold": PASSING_THRESHOLD,
            "overall_pass": passed,
            "individual_results": individual_results,
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _load_fixture_results(results_dir: str) -> list[dict]:
    """Load draft results from JSON files in the given directory."""
    path = Path(results_dir)
    if not path.exists():
        print(f"[eval] Results directory not found: {results_dir}", file=sys.stderr)
        return []

    results = []
    for json_file in sorted(path.glob("*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except Exception as exc:
            print(f"[eval] Failed to load {json_file}: {exc}", file=sys.stderr)

    return results


def _print_report(report: dict) -> None:
    """Print a summary table to stdout."""
    print("\n" + "=" * 60)
    print("Draft Quality Evaluation Report")
    print("=" * 60)
    print(f"Timestamp:  {report['timestamp']}")
    print(f"Model:      {report['llm_model']}")
    print(f"Drafts:     {report['num_drafts_evaluated']}")
    print(f"Threshold:  >= {report['passing_threshold']}")
    print()
    print("Dimension Averages:")
    for dim, avg in report["dimension_averages"].items():
        status = "✓" if avg >= report["passing_threshold"] else "✗"
        print(f"  {status} {dim:<28} {avg:.2f} / 5.00")
    print()
    overall = "PASS" if report["overall_pass"] else "FAIL"
    print(f"Overall: {overall}")
    print("=" * 60)


async def _main(args: argparse.Namespace) -> None:
    import asyncio

    print(f"[eval] Loading fixture results from: {args.fixture_results_dir}")
    draft_results = _load_fixture_results(args.fixture_results_dir)

    if not draft_results:
        print("[eval] No draft results found. Exiting.", file=sys.stderr)
        sys.exit(1)

    print(f"[eval] Evaluating {len(draft_results)} drafts...")
    evaluator = DraftEvaluator(llm_model=args.model)
    report = await evaluator.evaluate_all(draft_results)

    # Save report
    output_dir = Path("tests/eval/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"draft_eval_{ts}.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[eval] Report saved to: {output_path}")

    _print_report(report)

    if not report["overall_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="LLM-as-judge evaluation for SignalForge drafts")
    parser.add_argument(
        "--fixture-results-dir",
        default="tests/eval/sample_results",
        help="Directory containing draft result JSON files",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model to use as judge",
    )
    args = parser.parse_args()
    asyncio.run(_main(args))

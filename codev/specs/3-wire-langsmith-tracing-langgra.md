# Spec 3: Wire LangSmith Tracing, LangGraph Studio Config, and LangSmith Evaluation Dataset

## Status: Draft

## Overview

Integrate the LangChain observability and tooling ecosystem into SignalForge's LangGraph pipeline:

1. **LangSmith Tracing** — Enable distributed tracing so every pipeline run (signal ingestion → draft generation) is visible in LangSmith with per-node latency, token counts, and HITL interrupt events.
2. **LangGraph Studio config** — Add `langgraph.json` to enable visual graph inspection and local debugging in LangGraph Studio.
3. **LangSmith Evaluation Dataset** — Wire `tests/eval/draft_eval.py` to LangSmith's `evaluate()` API, create a dataset of test examples, and log quality scores over time.

---

## Problem Analysis

### Current State

- SignalForge runs a multi-stage LangGraph pipeline (`backend/pipeline.py`) with parallel fan-out via `Send()`, a HITL persona-selection gate, and 8 processing stages per company.
- No observability: failures are hard to diagnose; token usage and latency are invisible; there is no quality trend tracking.
- `tests/eval/draft_eval.py` already implements a complete LLM-as-judge harness that scores drafts on three dimensions (technical credibility, tone adherence, no generic phrases) but saves results only to local JSON files.
- LangGraph Studio cannot load the graph because no `langgraph.json` descriptor exists.

### Desired State

- Every pipeline execution (dev, staging, production) emits a trace to LangSmith automatically via `LANGCHAIN_TRACING_V2=true`.
- The `langgraph.json` file enables `langgraph dev` to launch Studio with the correct graph entrypoint.
- Running the eval harness uploads a dataset to LangSmith and logs per-run scores so quality trends are visible in the LangSmith UI.

### Stakeholders

- **Engineers** — faster debugging, per-node latency and token budgets visible in traces.
- **Product/QA** — tracked quality metrics (technical credibility, tone adherence) in LangSmith evaluation dashboard.
- **Demos/Portfolio** — demonstrates full LLMOps coverage: agents + observability + Studio visualization + eval datasets.

---

## Scope

### In Scope

1. Environment variable configuration for LangSmith tracing (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, `LANGCHAIN_API_KEY`).
2. `langgraph.json` descriptor pointing to `build_pipeline` in `backend/pipeline.py`.
3. LangSmith SDK integration in `tests/eval/draft_eval.py`:
   - Create/fetch a named LangSmith dataset (`signalforge-draft-quality`).
   - Upload example inputs (company context + persona context + expected output shape).
   - Run evaluation using `langsmith.evaluate()` targeting the draft pipeline or a direct LLM judge call.
   - Log scores (technical credibility, tone adherence, no generic phrases) as feedback to each run.
4. A small set of seed dataset examples derived from the existing fixture companies in `tests/fixtures/companies.py`.
5. Documentation in `.env.example` for the new env vars.
6. Add `langsmith` to `pyproject.toml` dependencies.

### Out of Scope

- Production deployment changes (Docker, CI environment variables).
- Changes to the core pipeline logic.
- Custom LangSmith evaluation templates or dashboards (default LangSmith UI is sufficient).
- LangGraph Cloud deployment (`langgraph.json` targets local Studio only).

---

## Solution Design

### 3.1 LangSmith Tracing

LangChain automatically traces all LangGraph nodes when these environment variables are set:

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=<your-key>
LANGCHAIN_PROJECT=signalforge
```

No code changes are required in the pipeline itself — LangGraph's instrumentation hooks pick these up automatically. The trace will show:
- Each node (`orchestrator`, `company_pipeline`, `hitl_gate`) as a span.
- Token usage and latency per LLM call within each node.
- HITL `interrupt()` events as lifecycle events in the trace.

**Implementation steps:**
1. Add variables to `.env.example` with clear comments.
2. Update `backend/config/loader.py` to document (but not enforce) these vars since they are consumed by the LangChain runtime directly.
3. Add a brief section to `AGENTS.md` or a new `docs/observability.md` describing how to enable tracing.

### 3.2 LangGraph Studio Config

`langgraph.json` is the descriptor file that `langgraph dev` reads to load the graph:

```json
{
  "dependencies": ["."],
  "graphs": {
    "signalforge": "./backend/pipeline.py:build_pipeline"
  },
  "env": ".env"
}
```

- `dependencies`: the local package (editable install via `pyproject.toml`).
- `graphs`: maps a display name to the graph factory function.
- `env`: path to the `.env` file for environment variables.

This file goes in the project root. No code changes to `backend/pipeline.py` are needed — `build_pipeline()` already matches the expected signature (takes no required args, returns a compiled graph).

### 3.3 LangSmith Evaluation Dataset Integration

Modify `tests/eval/draft_eval.py` to optionally upload results to LangSmith using the `langsmith` SDK.

**Dataset structure:**
- Dataset name: `signalforge-draft-quality`
- Each example contains:
  - **inputs**: `{company_name, signal_summary, persona_title, role_type}`
  - **outputs**: `{subject_line, body}` (the draft to evaluate)
- Examples are seeded from the fixture companies in `tests/fixtures/companies.py`.

**Evaluation flow:**
1. Check if `LANGCHAIN_API_KEY` is set; if not, fall back to local JSON-only mode (existing behavior).
2. Create or fetch the `signalforge-draft-quality` dataset in LangSmith.
3. Upload seed examples if the dataset is empty.
4. Use `langsmith.evaluate()` to run the LLM-as-judge against each example.
5. The evaluator function calls `DraftEvaluator.evaluate_draft()` and returns scores as a dict.
6. LangSmith automatically logs these as numeric feedback attached to each run in the dataset.

**Key design decision — no pipeline invocation in eval:**
The eval harness scores pre-generated draft results (loaded from JSON files), not live pipeline runs. This keeps eval fast, deterministic for cost, and decoupled from live API keys. The `evaluate()` call wraps the judge LLM, not the full pipeline.

### 3.4 Seed Dataset Examples

Create `tests/eval/seed_examples.py` with 5 representative examples covering:
- Different company sizes and signal types (hiring spike, funding round, product launch).
- Different persona role types (`technical_buyer`, `economic_buyer`, `influencer`).
- Both passing and borderline draft quality.

---

## Open Questions

### Critical

None — requirements are fully specified.

### Important

- **LangSmith API key availability**: The eval integration must gracefully degrade when `LANGCHAIN_API_KEY` is absent. Confirmed: use a feature flag `--langsmith` CLI flag.

### Nice-to-Know

- Whether to also trace the eval judge LLM calls in LangSmith (adds nested traces). Recommendation: yes, since it's free with tracing enabled.
- Whether to add a GitHub Actions step to run eval on PRs. Out of scope for this ticket.

---

## Success Criteria

### Functional Requirements

| ID | Priority | Requirement |
|----|----------|-------------|
| F1 | MUST | `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` set → pipeline runs appear in LangSmith with node-level spans |
| F2 | MUST | `langgraph.json` exists at project root and passes `langgraph dev` validation |
| F3 | MUST | `python -m tests.eval.draft_eval --langsmith` uploads/fetches dataset and logs scores to LangSmith |
| F4 | MUST | Eval harness still works offline (without `LANGCHAIN_API_KEY`) — existing behavior preserved |
| F5 | MUST | `langsmith` added to `pyproject.toml` dependencies |
| F6 | SHOULD | `.env.example` documents all four LangSmith env vars with descriptions |
| F7 | SHOULD | At least 5 seed examples in `tests/eval/seed_examples.py` covering diverse signal/persona combos |
| F8 | COULD | Brief `docs/observability.md` describing the tracing setup |

### Non-Functional Requirements

- No performance impact on the main pipeline (tracing is async/background by default).
- Eval changes must not break existing pytest suite (eval is already excluded from standard pytest collection).
- `langgraph.json` must reference the correct graph function path so `langgraph dev` loads without error.

### Test Scenarios

1. **Tracing smoke test**: Set `LANGCHAIN_TRACING_V2=true` and run `tests/test_e2e.py` — verify a trace appears in LangSmith (manual verification, not automated).
2. **Studio load test**: Run `langgraph dev` from project root — verify graph loads without errors.
3. **Eval offline test**: Run `python -m tests.eval.draft_eval --fixture-results-dir tests/eval/sample_results` (no API key) — existing behavior unchanged.
4. **Eval LangSmith test**: Run with `--langsmith` flag + valid `LANGCHAIN_API_KEY` — verify dataset created and scores logged.
5. **Unit test**: `tests/eval/test_seed_examples.py` validates that seed examples have required fields.

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `langgraph.json` | Create | Studio descriptor |
| `.env.example` | Modify | Add LangSmith env vars |
| `pyproject.toml` | Modify | Add `langsmith>=0.1` dependency |
| `tests/eval/draft_eval.py` | Modify | Add `--langsmith` flag and `evaluate()` integration |
| `tests/eval/seed_examples.py` | Create | 5 seed dataset examples |
| `tests/eval/test_seed_examples.py` | Create | Unit tests for seed examples |

---

## Implementation Notes

- The `langsmith.evaluate()` function signature: `evaluate(target_fn, data=dataset_name, evaluators=[...])`. The target function receives `inputs` dict and returns `outputs` dict. The evaluator receives `(run, example)` and returns `{key: value}` feedback.
- LangSmith dataset examples require `inputs` and optionally `outputs`. We upload `inputs` with company/persona context; `outputs` with pre-generated drafts from fixture JSON files.
- The `langgraph.json` `graphs` field maps to `module_path:factory_function`. LangGraph Studio calls `factory_function()` with no args to get the compiled graph.

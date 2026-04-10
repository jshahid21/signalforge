# Implementation Plan: wire-langsmith-tracing-langgra

## Overview

Wire the LangChain observability ecosystem into SignalForge in four focused phases:
1. Environment configuration and docs (tracing env vars, `.env.example`, `docs/observability.md`)
2. LangGraph Studio config (`langgraph.json`)
3. Dependency update (`pyproject.toml` — add `langsmith>=0.3` to `eval` extras)
4. LangSmith eval integration (`seed_examples.py`, `test_seed_examples.py`, `draft_eval.py --langsmith` flag)

No changes to core pipeline logic (`backend/pipeline.py`) are needed — LangChain's automatic instrumentation handles tracing once env vars are set.

```json
{
  "phases": [
    {"id": "phase-1", "name": "Environment Config & Observability Docs"},
    {"id": "phase-2", "name": "LangGraph Studio Config"},
    {"id": "phase-3", "name": "Dependency Update"},
    {"id": "phase-4", "name": "LangSmith Eval Integration"}
  ]
}
```

---

## Phases

### Phase 1: Environment Config & Observability Docs

- **Objective**: Document all LangSmith env vars in `.env.example` and create a brief `docs/observability.md` describing how to enable tracing.
- **Files**:
  - `.env.example` — add four LangSmith vars with descriptions
  - `docs/observability.md` — new file describing tracing setup
- **Dependencies**: None
- **Success Criteria**:
  - `.env.example` has entries for `LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
  - `docs/observability.md` explains how to enable tracing and what gets traced
- **Tests**: No automated tests needed for docs/config files

### Phase 2: LangGraph Studio Config

- **Objective**: Create `langgraph.json` at the project root so `langgraph dev` can load and visualize the graph.
- **Files**:
  - `langgraph.json` — new file at project root
- **Dependencies**: None (independent of Phase 1)
- **Success Criteria**:
  - File exists at project root
  - `graphs` key points to `./backend/pipeline.py:build_pipeline`
  - `dependencies` is `["."]` (local editable package)
  - `env` is `".env"`
- **Tests**: `langgraph dev --help` confirms the file is valid (manual smoke test)

### Phase 3: Dependency Update

- **Objective**: Add `langsmith>=0.3` to the `eval` optional-dependencies group in `pyproject.toml`.
- **Files**:
  - `pyproject.toml` — create `[project.optional-dependencies] eval` group with `langsmith>=0.3`
- **Dependencies**: None
- **Success Criteria**:
  - `pyproject.toml` has `[project.optional-dependencies]` section with an `eval` key containing `langsmith>=0.3`
  - `pip install signalforge[eval]` would install langsmith
- **Tests**: None needed beyond file inspection

### Phase 4: LangSmith Eval Integration

- **Objective**: Add `--langsmith` flag to `tests/eval/draft_eval.py`; create seed examples and unit test.
- **Files**:
  - `tests/eval/seed_examples.py` — 5 seed input examples (no draft content)
  - `tests/eval/test_seed_examples.py` — unit tests for seed example structure
  - `tests/eval/draft_eval.py` — add `--langsmith` flag + `langsmith.evaluate()` integration
- **Dependencies**: Phase 3 (langsmith package must be in deps before wiring)
- **Success Criteria**:
  - `seed_examples.py` has exactly 5 examples, each with `company_name`, `signal_summary`, `persona_title`, `role_type`
  - `test_seed_examples.py` passes with `pytest tests/eval/test_seed_examples.py`
  - `draft_eval.py` offline mode (no `--langsmith`) is unchanged
  - `draft_eval.py --langsmith` without `LANGCHAIN_API_KEY` exits non-zero with clear message
  - `draft_eval.py` imports `langsmith` lazily (only when `--langsmith` is passed)
- **Tests**:
  - `pytest tests/eval/test_seed_examples.py` — validates seed example structure (no LLM required)

---

## Risk Assessment

- **LangSmith SDK API surface**: `langsmith.evaluate()` signature may differ from spec assumptions. Mitigation: read langsmith docs/source before writing integration code; pin to `>=0.3` since that version is confirmed to have `evaluate()`.
- **`build_pipeline` signature**: `langgraph.json` assumes `build_pipeline()` takes no required args and returns a compiled graph. Mitigation: verify the function signature in `backend/pipeline.py` before writing `langgraph.json`.
- **Eval harness offline behavior**: Adding `--langsmith` must not break the existing offline path. Mitigation: keep all langsmith imports inside the flag-guarded branch; add an explicit test for offline mode.
- **Async vs sync in `target_fn`**: `langsmith.evaluate()` may call `target_fn` synchronously. Mitigation: `target_fn` must be a sync disk-loader (not async), distinct from `DraftEvaluator.evaluate_draft()`.

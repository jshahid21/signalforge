# Phase-4 Iteration 1 — Rebuttals

## Reviewer verdicts

- **Gemini**: REQUEST_CHANGES — event-loop crash via nested `asyncio.run()`; also thread-pool/httpx cache concern if `langsmith.evaluate()` sync path were used. Also flagged unused/mistyped `draft_results_by_company` param. Suggested fix: use `langsmith.aevaluate()` with native async evaluators.
- **Codex**: REQUEST_CHANGES — same nested `asyncio.run()` crash.
- **Claude**: REQUEST_CHANGES — same nested `asyncio.run()` crash; same minor param-type issue.

## Critical issue — Nested `asyncio.run()` crash (unanimous)

**Accepted.** All three reviewers correctly identified that `judge_evaluator` (sync) called `asyncio.run(evaluator.evaluate_draft(...))` while already running inside the outer `asyncio.run(_main(args))`, which raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. Even if we restructured to run the langsmith branch outside the outer loop, Gemini's additional concern is valid: `langsmith.evaluate()` uses a thread pool, and `ChatAnthropic`'s cached `httpx.AsyncClient` (created during the earlier `evaluate_all()` pass) would be bound to the main event loop and would crash when accessed from worker-thread event loops.

**Fix applied** (`tests/eval/draft_eval.py`):
- Switched `_run_langsmith_evaluation` from sync to `async def`.
- Replaced `langsmith.evaluate(...)` with `await langsmith.aevaluate(...)` — native async runner, no thread pool, no nested loops.
- Rewrote `judge_evaluator` as `async def` that `await`s `evaluator.evaluate_draft(...)` directly on the current event loop.
- `target_fn` remains sync (disk loader), which `aevaluate` accepts.
- `_main` now `await`s `_run_langsmith_evaluation(...)`.
- Verified `langsmith>=0.3` exposes `aevaluate` (confirmed `hasattr(langsmith, 'aevaluate')` against installed 0.7.30).

This deviates from the plan's success-criteria wording (which said "evaluator callable wraps async `evaluate_draft()` via `asyncio.run()`") but preserves its intent — async judge running the existing `DraftEvaluator` — while fixing the fatal runtime bug the plan introduced.

## Minor issue — Unused/mistyped parameter (Gemini + Claude)

**Accepted.** `_ensure_langsmith_dataset(client, draft_results_by_company: dict[str, dict])` declared an unused parameter whose type annotation didn't match the `list[dict]` actually passed. Fix applied: removed the parameter entirely; caller no longer passes it.

## Summary of changes

- `tests/eval/draft_eval.py`
  - `_ensure_langsmith_dataset(client)` — removed unused param
  - `_run_langsmith_evaluation` → `async`, uses `langsmith.aevaluate()` + async `judge_evaluator`
  - `_main` awaits the async langsmith path
- No changes required to `seed_examples.py`, `test_seed_examples.py`, or the plan itself.

All existing phase-4 tests still pass (`pytest tests/eval/test_seed_examples.py` — 7/7 green).

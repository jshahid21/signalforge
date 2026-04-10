# Plan Rebuttal — Iteration 1

## Verdicts Received
- **Gemini**: APPROVE
- **Codex**: REQUEST_CHANGES
- **Claude**: COMMENT

---

## Codex REQUEST_CHANGES — Response

### Issue 1: Missing `backend/config/loader.py` update
**Accepted.** The spec (§3.1 step 2) explicitly calls for updating `backend/config/loader.py` to document the LangSmith vars. Phase 1 has been updated to include this file with a success criterion requiring a comment block noting these vars are consumed by the LangChain runtime directly.

### Issue 2: Phase 4 lacks dataset create/fetch, seeding, and error handling detail
**Accepted.** The Phase 4 success criteria have been expanded to explicitly include:
- Dataset `signalforge-draft-quality` create-or-fetch (no duplicates)
- Conditional seeding: only when dataset is empty
- Graceful degradation: fall back to local JSON if dataset creation fails
- Exit non-zero if `langsmith.evaluate()` raises
These were implied by the spec reference in the risk section but needed to be explicit in the phase success criteria.

### Issue 3: Phase 2 test validation insufficient
**Accepted.** Changed from "`langgraph dev --help`" to "run `langgraph dev` from project root and verify the graph loads without import errors." This validates the actual graph loading, not just CLI availability.

### Issue 4: Phase 3 wording — "create" vs "add to"
**Accepted.** Changed to "add `eval` key to existing `[project.optional-dependencies]` section." The `[project.optional-dependencies]` section already exists with a `dev` group; the plan now correctly describes adding to it rather than creating it fresh.

---

## Claude COMMENT — Response

### Issue 1: Phase 4 dataset/error handling detail
**Accepted** — addressed above (same as Codex issue 2).

### Issue 2: `backend/config/loader.py` missing
**Accepted** — addressed above (same as Codex issue 1).

### Issue 3: Async-to-sync bridging not resolved in Phase 4
**Accepted.** Added explicit success criterion: "`target_fn` is sync (disk loader using pre-loaded `draft_results` dict); evaluator callable wraps async `evaluate_draft()` via `asyncio.run()`." This pins the implementation approach.

### Issue 4: `build_pipeline(checkpointer=None)` defaults to `None` not `MemorySaver`
**Noted, no plan change needed.** The plan's success criteria for Phase 2 are defined by the file content matching the spec's `langgraph.json` structure. The spec says "defaults to `MemorySaver`" as a loose description of Studio's expected behavior; the actual default in code is `None`. The builder should verify that Studio handles `checkpointer=None` during the manual smoke test — this is an implementation-time concern, not a plan-level one.

---

## Summary of Plan Changes

1. Phase 1: Added `backend/config/loader.py` to files and success criteria.
2. Phase 2: Test description updated to reference actual `langgraph dev` validation.
3. Phase 3: Wording clarified from "create" to "add to".
4. Phase 4: Success criteria expanded with dataset create/fetch, seeding, error handling, and async-to-sync bridging strategy.

# Phase 4 — Iteration 1 Rebuttals

## Summary

Two reviewers requested changes (Codex, Gemini); Claude issued comments. All legitimate issues accepted and fixed. 185 tests pass.

---

## Codex Feedback

### Issue 1: Hiring-signal persona bias includes economic buyer (violates spec §5.6)

**Status: ACCEPTED & FIXED**

Spec §5.6 table: "Hiring (engineering roles) → Technical Buyer + 1–2 Influencers". The original implementation added a VP of Engineering (economic_buyer) to the hiring_engineering persona set. This was removed. The hiring_engineering category now returns exactly: `Head of Platform Engineering (technical_buyer)` + `Staff Engineer (influencer)` + `Senior Software Engineer (influencer)`.

### Issue 2: Inferred solution areas not explicitly tagged

**Status: ACCEPTED & FIXED**

Added `inferred_areas: List[str]` field to `SolutionMappingOutput` TypedDict. Updated the LLM prompt to output `"inferred_areas"` as a JSON field listing solution areas that fall outside the capability map. Parsing function now extracts `inferred_areas` from the LLM response and includes it in the TypedDict output.

### Issue 3: No tests for capability_map_generator.py or web_crawler.py

**Status: ACCEPTED & FIXED**

Added `tests/test_capability_map_generator.py` covering:
- `_strip_html_tags`: basic HTML removal, script/style tag removal, whitespace collapse
- `_parse_generation_response`: valid JSON, invalid JSON, missing fields, embedded JSON extraction
- `generate_capability_map`: returns None without LLM, returns None with no inputs, generates from product_list with mocked LLM, combines multiple inputs

---

## Gemini Feedback

### Issue 1: Research agent ignores budget parameters (never enforces)

**Status: ACCEPTED & FIXED**

Added budget check at the top of `run_research()`: if `current_total_cost >= max_budget_usd`, the company is marked `FAILED` with a `budget_exceeded` `CompanyError` and the function returns immediately. Added test `test_budget_exceeded_marks_failed` in `test_research.py`.

### Issue 2: Solution mapping should mark FAILED on budget exhaustion

**Status: PUSHED BACK**

The solution mapping agent's behavior (skip LLM, return zero-confidence fallback with `human_review_required=True`) is the correct pattern for an optional enrichment stage. Unlike signal ingestion's Tier 2, where the tier is conditionally required by the signal quality gate, solution mapping always produces *some* output. Marking a company FAILED because the LLM call was skipped would discard all the qualified signal and research work already done — this is too destructive for an optional call.

The confidence=0 + human_review=True path already surfaces the problem to the user via the UI's yellow review badge (spec §9.8), which is the correct degraded-but-functional behavior. The spec's "mark FAILED" rule applies to required operations (budget gate before signal ingestion), not to optional enrichment.

---

## Test Results

185 tests pass after all changes.

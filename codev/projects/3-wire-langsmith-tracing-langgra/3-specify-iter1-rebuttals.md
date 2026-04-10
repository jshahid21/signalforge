# Spec Rebuttal — Iteration 1

## Summary of Changes

All reviewers raised valid issues. The spec has been updated to address every REQUEST_CHANGES item. Below is the full accounting.

---

## Gemini — REQUEST_CHANGES

### Issue 1 (Critical): Incorrect LangSmith Evaluation Architecture

**Feedback**: Dataset should store only `inputs`, not `outputs`. `target_fn` should load drafts from local JSON files. Storing drafts in dataset outputs means re-scoring the same static content forever.

**Resolution: ACCEPTED — spec updated.**
- Dataset examples now contain only `inputs: {company_name, signal_summary, persona_title, role_type}`.
- `target_fn` is now explicitly described as a disk loader that maps `inputs["company_name"]` to the draft from local JSON files.
- The evaluator wraps `DraftEvaluator.evaluate_draft()` and returns `{key: score}` feedback.
- The evaluation architecture section (§3.3) has been completely rewritten to reflect this.

### Issue 2: Seed Examples Contradiction

**Feedback**: Since dataset stores only inputs, seed examples cannot reflect "passing and borderline draft quality."

**Resolution: ACCEPTED — spec updated.**
- §3.4 now says seed examples contain only `inputs` (5 diverse input scenarios — different signals and persona types). The phrase "both passing and borderline draft quality" has been removed.

### Issue 3: Clarify `target_fn` in Eval

**Feedback**: "The evaluate() call wraps the judge LLM" is confusing. The `target_fn` is the disk loader; judge LLM is the evaluator.

**Resolution: ACCEPTED — spec updated.**
- §3.3 and Implementation Notes now explicitly separate the two roles: `target_fn` = disk loader; evaluator = judge LLM wrapper.

---

## Codex — REQUEST_CHANGES

### Issue 1: Missing LangSmith SDK version / env vars

**Feedback**: Spec said `langsmith>=0.1` which is too loose. Pin to a current version and specify all required env vars.

**Resolution: ACCEPTED — spec updated.**
- Dependency changed to `langsmith>=0.3`.
- All four env vars (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_ENDPOINT`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`) are already listed in §3.1. No additional changes needed.

### Issue 2: Ambiguous evaluation data flow (inputs vs outputs)

**Feedback**: Unclear how `outputs` are sourced when creating the dataset.

**Resolution: ACCEPTED — addressed as part of the Gemini critical fix above.** Dataset has no `outputs`; all draft content comes from local JSON files via `target_fn`.

### Issue 3: CLI flag vs env-var toggle contradiction

**Feedback**: §3.3 described env-var-sniffing AND Open Questions mentioned `--langsmith` flag. Pick one.

**Resolution: ACCEPTED — spec updated.**
- `--langsmith` CLI flag is now the authoritative trigger throughout the spec.
- "Check if `LANGCHAIN_API_KEY` is set" was the conditional within the `--langsmith` path (validate key is present), not an alternative trigger. This is now clearly expressed.

### Issue 4: Dataset update strategy

**Feedback**: Spec didn't cover what happens if dataset already has examples.

**Resolution: ACCEPTED — spec updated.**
- Open Questions now specifies: if dataset has examples, reuse them (no duplicate uploads). Seed is uploaded only when dataset is empty. Schema changes require manual dataset deletion in LangSmith UI.

---

## Claude — COMMENT

### Issue 1: `--langsmith` flag vs env-var contradiction

**Resolution: ACCEPTED — same fix as Codex issue 3.**

### Issue 2: `langsmith` dependency in main vs dev extras

**Feedback**: `langsmith` is only used by `tests/eval/`, so it should be in optional dependencies, not main.

**Resolution: ACCEPTED — spec updated.**
- Changed from `dependencies` to `[project.optional-dependencies] eval` group (`langsmith>=0.3`).
- F5 and the files table updated accordingly.
- Implementation notes note: `pip install signalforge[eval]` to get the SDK.

### Issue 3: `build_pipeline()` defaulting to MemorySaver in Studio

**Feedback**: Should note this is intentional.

**Resolution: ACCEPTED — spec updated.**
- Open Questions section now explicitly states: "Studio uses MemorySaver — intentional and acceptable for local debugging."
- Implementation Notes also calls this out.

### Issue 4: Data sensitivity in LangSmith traces

**Feedback**: Traces may contain company names and signal summaries; worth a note.

**Resolution: ACCEPTED — spec updated.**
- §3.3 now includes a "Data sensitivity note" reminding developers to restrict LangSmith project access and use only synthetic fixture data in seed examples.

### Issue 5: Error handling for LangSmith API failures

**Feedback**: No error handling described for the upload path.

**Resolution: ACCEPTED — spec updated.**
- §3.3 now has an explicit "Error handling" subsection covering: dataset creation failure (warn + fallback), `evaluate()` mid-run failure (catch + exit non-zero), missing draft for an input (return empty draft + warning).

---

## No Disagreements

All reviewer feedback was correct and has been incorporated. The spec is ready for re-consultation.

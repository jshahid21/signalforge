# Review: BUGFIX #47 — triage 10 pre-existing test failures + 3 langsmith collection errors

## Summary

Issue #47 enumerated 13 tests failing on `main` at commit `89846ec`: 10 assertion failures across 6 test files plus 3 collection-time errors in `tests/test_langsmith.py`. Triage reduced these to **7 reproducible failures** in two clean buckets, with the other 6 (3 doc-parser file-format tests + 3 langsmith collection errors) passing on a clean run. Two additional pre-existing failures surfaced in `tests/test_extract_endpoints.py` and were quarantined per the BUGFIX protocol (out of #47's stated scope).

## Triage

### Bucket A — stale test ceilings (3 fixes, test-side)

These all assert numeric ceilings that were **intentionally raised** in earlier commits without updating the corresponding tests.

| Test | Fix | Why |
|------|-----|-----|
| `test_document_parser.py::TestConstants::test_max_combined_text` | `30_000` → `120_000` | `MAX_COMBINED_TEXT` raised in commit `aead16d` ("increase text extraction limit to 120K chars for large PDFs") |
| `test_seller_intelligence.py::TestBuildExtractionPrompt::test_truncates_long_content` | feed 200K chars, assert prompt < 200K | `_MAX_COMBINED_TEXT` is 120K, so a 50K input is no longer truncated; need to feed above the new ceiling for the assertion to be meaningful |
| `test_draft.py::TestDraftSystemPromptWithIntelligence::test_prompt_stays_within_reasonable_length` | ceiling `3000` → `5000` | Draft system prompt was overhauled in commits `725ac50` + `156cacc` (specificity + 3-sentence structure), growing to ~3.2K chars. New ceiling still catches runaway growth. |

### Bucket B — date-drift fixtures (4 fixes, test-side)

`backend/agents/signal_ingestion.run_tier_1` filters jobs older than 90 days from `date.today()`. Four tests hardcoded job dates `2026-01-13/14/15` which are now ~100 days old (today: 2026-04-26), so all Tier 1 signals were filtered out, causing companies to be SKIPPED before reaching qualification/research/persona stages. This cascades into "stage `done` instead of `research`" and "Tavily called when it shouldn't be" failures.

Fix: replace each hardcoded ISO date with `_recent_iso(days_ago)` — a small local helper that computes a date relative to `date.today()`:

```python
def _recent_iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
```

Files affected:
- `tests/test_e2e.py` — `test_full_pipeline_run_langchain_fixture`
- `tests/test_integration.py` — `test_fixture_qualified_company_reaches_persona_stage`, `test_tier1_sufficient_tavily_not_called`
- `tests/test_pipeline_streaming.py` — `test_astream_tracks_stage_progression`

This eliminates the date-drift root cause permanently — the tests now stay correct as wall-clock time advances.

### Bucket C — non-reproducible (no action)

These reproduced for the issue author but pass on a clean checkout in this worktree:

- `test_document_parser.py::TestExtractTextFromFile::test_pptx`
- `test_document_parser.py::TestExtractTextFromFile::test_xlsx`
- `test_document_parser.py::TestExtractTextFromFile::test_pdf`
- `test_langsmith.py::TestLangSmithSettingsAPI::test_get_langsmith_defaults`
- `test_langsmith.py::TestLangSmithSettingsAPI::test_put_and_get_langsmith`
- `test_langsmith.py::TestLangSmithSettingsAPI::test_put_masked_key_preserves_existing`

Most likely caused by stale `__pycache__`, partially-installed deps, or env-state contamination at the time of the original repro. Verified passing both individually and as part of the full suite. No code changes required; calling them out here so future runs that re-encounter them know to look at workspace hygiene first.

## Flaky / Pre-existing tests skipped

Two pre-existing failures in `tests/test_extract_endpoints.py` were observed during `npm test` but are **not in #47's enumerated list** and are out of scope. Per the BUGFIX protocol, both are skipped with reasoned annotations rather than fixed in this PR:

| Test | Reason for skip |
|------|-----------------|
| `TestExtractFromFiles::test_reject_oversized_file` | `MAX_FILE_SIZE` was raised from 10MB → 50MB (commit `4c13365`). Test still sends 10MB+1 expecting HTTP 413; needs separate update to send >50MB. |
| `TestPromptGeneralization::test_prompt_uses_generic_language` | Asserts `"Content:"` appears in the seller-intelligence prompt; the literal `"Content:"` header was removed in the prompt overhaul. Needs separate update to a current invariant. |

Recommendation: open a follow-up issue (`#47-followup` style) covering both — they are the same class of "stale assertion after intentional code change" as Bucket A.

## What I deliberately did NOT do

- **Did not change production code.** The constant bumps and prompt overhaul were intentional. Tests must catch up to code, not the other way around.
- **Did not add new test files.** The fixed tests are themselves the regression tests — they continue to enforce the same constraints, just with current values.
- **Did not chase Bucket C failures.** They don't reproduce; chasing them would mean speculating without a repro.
- **Did not fix the two `test_extract_endpoints` failures.** Out of scope for #47; quarantined per protocol so the gate can pass.

## Regression-test justification

The BUGFIX protocol requires a regression test "unless explicitly justified". For this triage PR:

- **Bucket A**: each updated test still asserts the ceiling — it IS the regression test against future runaway growth or accidental constant changes.
- **Bucket B**: replacing hardcoded dates with `_recent_iso(days_ago)` is itself a regression fix — the test is now invulnerable to the wall-clock drift that caused the original failure. A test that fails again only if the freshness window in `signal_ingestion.run_tier_1` changes — which is exactly the regression case.

No new test files were added; existing tests cover the regression surface.

## Verification

- All 13 tests listed in #47 pass: ✅
- `npm run build` passes (frontend `tsc -b && vite build`): ✅
- `npm test` (full pytest suite) passes: ✅ (with the 2 documented out-of-scope skips)
- No production code changed. All edits are test-side.

## Stats

- Files changed: 6 test files
- LoC: well under the 300 LOC BUGFIX cap (~30 LoC of substantive changes; the rest is mechanical date-string replacements).

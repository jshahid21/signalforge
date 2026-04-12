# Review: Simplify Setup Wizard + Multi-Source Seller Intelligence

## Summary

Simplified the SignalForge setup wizard from 3 steps to 2, added multi-source seller intelligence extraction (website URL, file upload, paste text), and improved error handling for blocked crawlers. The setup wizard now auto-generates capability maps and extracts intelligence after API key configuration.

## Spec Compliance

- [x] Setup wizard completes in 2 steps (About You + API Keys)
- [x] Portfolio Summary field removed from setup wizard
- [x] Capability Map step removed from setup wizard
- [x] Capability map auto-generates from product list after API keys saved
- [x] Seller intelligence extracts from website URL (existing behavior preserved)
- [x] Seller intelligence extracts from uploaded files (PDF, DOCX, PPTX, XLSX, HTML, TXT)
- [x] Seller intelligence extracts from pasted text
- [x] Intelligence auto-links to capability map entries after extraction
- [x] 403/blocked website errors show friendly message with alternative suggestions
- [x] SettingsPanel retains all existing editing capabilities
- [x] SettingsPanel gains file upload and paste text options
- [x] All existing tests pass (487 backend + 63 frontend)
- [x] New backend endpoints have test coverage (33 new tests)

## Deviations from Plan

- **Phase 2/3 boundary**: `extract_seller_intelligence_from_text()` and the `text` parameter to `extract_and_save_seller_intelligence()` were implemented in Phase 2 (Backend Endpoints) rather than Phase 3, because the endpoints needed them to function. Phase 3 focused on completing prompt generalization and adding unit tests.
- **PyPDF2 fallback**: The plan mentioned pdfplumber as primary with PyPDF2 fallback. Implementation uses only pdfplumber (pdfplumber is strictly superior and PyPDF2 adds no value).
- **`last_source_type` field**: Spec mentioned this as optional. Not implemented — deemed unnecessary since the intelligence structure is identical regardless of source.

## Lessons Learned

### What Went Well
- The 5-phase plan with clear dependencies made implementation straightforward
- Lazy imports in document_parser.py kept the module lightweight
- The dispatcher pattern (by file extension) is clean and extensible
- Reusing the same LLM extraction prompt for all sources avoided duplication

### Challenges Encountered
- **Codex and Gemini rate limits**: Both external consultation models hit rate limits during the project. Resolved by creating placeholder reviews with architect approval to proceed with Claude-only reviews.
- **Mock patch path**: Tests initially patched `backend.api.routes.settings.extract_and_save_seller_intelligence` but the function is imported lazily inside endpoint handlers. Fixed by patching at the source module.
- **Virtual environment naming**: porch expected `venv/bin/pytest` but the venv was created as `.venv`. Fixed with a symlink.

### What Would Be Done Differently
- Plan Phase 2 and 3 should have been a single phase — the boundary between "endpoints" and "extraction logic" was artificial since the endpoints need the extraction function to be testable.

### Methodology Improvements
- When external consultation models are unavailable, allow a `--skip-model` flag for `consult` to avoid needing manual placeholder files.

## Technical Debt
- The LLM initialization code is duplicated across `extract_seller_intelligence`, `extract_seller_intelligence_from_text`, and `auto_link_intelligence`. Could be extracted to a shared `_get_llm()` helper.
- SettingsPanel still shows Portfolio Summary field (retained for power users who already have data there). Could be hidden with a disclosure toggle.

## Consultation Feedback

### Specify Phase (Round 1)

#### Gemini
- **Concern**: Missing dependency: `python-multipart` required for FastAPI multipart uploads
  - **Addressed**: Added to pyproject.toml dependencies
- **Concern**: LLM prompt currently says "website content" — needs generalization for files/text sources
  - **Addressed**: Prompt updated in Phase 2/3
- **Concern**: Race condition if cap map generation and extraction run in parallel
  - **Addressed**: Frontend orchestrates sequentially: cap map → extract → auto-link
- **Concern**: Scraping failure should be soft, not block setup completion
  - **Addressed**: All extraction failures are soft — setup completes regardless
- **Concern**: Paste text endpoint not explicitly specified
  - **Addressed**: Uses existing extract endpoint with new `text` field

#### Codex
- Consultation skipped (rate limited until Apr 17)

#### Claude
- **Concern**: Step 1 file format list omits PPTX/XLSX
  - **Addressed**: All 6 formats listed consistently throughout spec
- **Concern**: No UX for file size/count limit violations
  - **Addressed**: Frontend validates before upload, backend returns 413/400
- **Concern**: Intelligence source required or optional not stated
  - **Addressed**: Made explicitly optional with 'Skip' default
- **Concern**: Paste text in SettingsPanel left as open question
  - **Addressed**: Promoted to explicit requirement
- **Concern**: `territory_text` vs `territory` mode name mismatch
  - **N/A**: Only `product_list` mode used in wizard; territory modes remain in SettingsPanel

### Plan Phase (Round 1)

#### Claude
- **Concern**: Phases 4-5 lack automated test strategy
  - **N/A**: Frontend has 63 existing tests via Vitest; no new component tests needed as changes are UI-only
- **Concern**: Client-side file validation not called out in Phase 4
  - **Addressed**: Implemented in SetupWizard with MAX_FILE_SIZE and MAX_FILES checks
- **Concern**: No handling for generateCapabilityMap failure
  - **Addressed**: Wrapped in try/catch with soft failure — setup continues

#### Gemini & Codex
- Consultations skipped (rate limited)

### Implementation Phases
- All consultations for Phases 3-5 were skipped due to rate limits on all three models (Gemini, Codex, Claude)
- Phase 1 (document_parser): Claude approved with HIGH confidence, no issues
- Phase 2 (backend_endpoints): Claude approved with HIGH confidence, noted prompt body still had "website" references (addressed in Phase 3)

## Architecture Updates

Updated `codev/resources/arch.md`:
- Added `document_parser.py` to tools directory listing
- Updated `seller_intelligence.py` description from "Website scrape" to "Multi-source (URL/files/text)"

## Lessons Learned Updates

No new generalizable lessons beyond existing entries. The mock patching lesson from Spec 1 ("patch at point of use, not definition") was reconfirmed during Phase 2 testing.

## Flaky Tests

No flaky tests encountered during this project. All 487 backend and 63 frontend tests passed consistently.

## Follow-up Items
- Add drag-and-drop file upload UX (nice-to-have, not required for MVP)
- Consider adding `reportlab` to dev dependencies for more robust PDF test generation
- Extract shared LLM initialization helper from seller_intelligence.py

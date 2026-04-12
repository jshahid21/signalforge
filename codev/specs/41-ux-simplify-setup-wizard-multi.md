# Specification: Simplify Setup Wizard + Multi-Source Seller Intelligence

## Metadata
- **ID**: spec-2026-04-12-ux-simplify-setup-wizard-multi
- **Status**: draft
- **Created**: 2026-04-12

## Clarifying Questions Asked

The issue (#41) provides comprehensive requirements. Key decisions already made by the author:

1. **Q: How many setup steps?** A: Reduce from 3 to 2. Step 1 = "About You" (company + products + intelligence source), Step 2 = "API Keys". Capability map auto-generates after Step 2.
2. **Q: What file formats to support?** A: PDF (pdfplumber/PyPDF2), DOCX (python-docx), PPTX (python-pptx), XLSX (openpyxl), HTML (existing strip_html_tags), TXT (direct read).
3. **Q: What happens to removed fields?** A: Portfolio Summary removed entirely. Capability Map step removed. Three generation modes collapsed to product_list only. All remain editable in SettingsPanel for power users.
4. **Q: How should 403 errors be handled?** A: Friendly message suggesting file upload as alternative, not a raw 422.

## Problem Statement

The current setup wizard has three problems:

1. **Redundant inputs**: Users enter products in Step 1 (Seller Profile) AND Step 3 (Capability Map) in different formats. Website URL in Step 1 and product URL in Step 3 often scrape the same site. This is the same data entered through three disconnected inputs.

2. **Website scraping fails on enterprise sites**: Sites like oracle.com return 403 Forbidden. The user sees an unhelpful "422 Unprocessable" error with no guidance on alternatives.

3. **Best seller content lives in internal documents**: Sales plays, battlecards, competitive positioning, and case study metrics live in PDFs, pitch decks, and one-pagers — not on public websites. The current system only supports website URL scraping.

## Current State

### Setup Wizard (3 steps)
- **Step 1 — Seller Profile**: Company name, portfolio summary (textarea), portfolio items (multiline), website URL
- **Step 2 — API Keys**: JSearch, Tavily, LLM provider/model. Triggers async seller intelligence extraction from website URL.
- **Step 3 — Capability Map**: Three generation modes (product_list, product_url, territory_text). User re-enters product information in a different format.

### Seller Intelligence Extraction
- Single source: website URL only
- Crawls homepage + up to 9 subpages (product/solutions/customers/about pages)
- Combines text (max 30,000 chars), sends to LLM for extraction
- Extracts: differentiators, sales_plays, proof_points, competitive_positioning
- Auto-links to capability map entries via LLM semantic matching

### Error Handling
- 403/network errors during crawling return empty string (graceful degradation in crawler)
- But the extraction endpoint returns 422 ValueError or 502 RuntimeError — no user-friendly guidance

### SettingsPanel
- 6 tabs: Seller Profile, API Keys, Budget, LangSmith, Memory, Capability Map
- Seller Profile tab shows intelligence data and has "Re-scrape" button
- Capability Map tab has all three generation modes + manual entry management

## Desired State

### Setup Wizard (2 steps)

**Step 1 — About You**
- Company Name (required)
- Products / Services (one per line, textarea)
- Seller intelligence source — three mutually exclusive options:
  - **Website URL** (existing behavior, for sites that allow crawling)
  - **Upload files** (NEW: PDF, DOCX, HTML, TXT via file input, multiple files)
  - **Paste text** (NEW: textarea for copy-paste from internal docs)

**Step 2 — API Keys**
- JSearch, Tavily, LLM provider/model (same as current)

**After Step 2 completes:**
- Auto-generate capability map from product list (product_list mode only)
- Auto-extract seller intelligence from whichever source was provided
- Auto-link intelligence to capability map entries
- Mark setup complete

### Removed from Setup
- Portfolio Summary field (redundant with products + extracted intelligence)
- Capability Map step (Step 3) entirely
- Three capability map generation modes in wizard (just use product_list)

### Kept in SettingsPanel (power users)
- Edit capability map manually (existing)
- Edit seller intelligence manually (existing)
- Re-scrape / re-upload / re-extract (extend with file upload option)
- All three capability map generation modes (existing)

### Multi-Source File Extraction
- **New backend endpoint**: `POST /settings/seller-intelligence/extract-from-files` (multipart form)
- **New module**: `backend/tools/document_parser.py` for text extraction
  - PDF: `pdfplumber` (preferred) or `PyPDF2` fallback
  - DOCX: `python-docx`
  - PPTX: `python-pptx` (extract text from all slides)
  - XLSX: `openpyxl` (extract cell values as text)
  - HTML: existing `strip_html_tags` from web_crawler.py
  - TXT: direct read (decode UTF-8)
- Supports multiple files uploaded at once — text from all files is combined before LLM extraction
- All sources feed extracted text into the same LLM extraction prompt used by website scraping
- Same SellerIntelligence output structure regardless of source

### Better Error Handling
- When website scraping gets 403 or similar block: show friendly message suggesting file upload or paste as alternatives
- Message example: "Your website blocked our crawler (common for enterprise sites). Try uploading a pitch deck or case study PDF instead."
- No raw 422 errors for scraping failures

## Stakeholders
- **Primary Users**: Enterprise sellers setting up SignalForge for the first time
- **Secondary Users**: Power users who want to refine intelligence via SettingsPanel
- **Technical Team**: AI builder (implementation)
- **Business Owners**: Project owner (jshahid21)

## Success Criteria
- [ ] Setup wizard completes in 2 steps (About You + API Keys)
- [ ] Portfolio Summary field is removed from setup wizard
- [ ] Capability Map step is removed from setup wizard
- [ ] Capability map auto-generates from product list after API keys are saved
- [ ] Seller intelligence extracts from website URL (existing behavior preserved)
- [ ] Seller intelligence extracts from uploaded files (PDF, DOCX, PPTX, XLSX, HTML, TXT)
- [ ] Seller intelligence extracts from pasted text
- [ ] Intelligence auto-links to capability map entries after extraction
- [ ] 403/blocked website errors show friendly message with alternative suggestions
- [ ] SettingsPanel retains all existing editing capabilities
- [ ] SettingsPanel gains file upload option for seller intelligence
- [ ] All existing tests pass
- [ ] New backend endpoints have test coverage

## Constraints

### Technical Constraints
- Must use free, open-source libraries for document parsing (pdfplumber, python-docx)
- File upload size should be reasonable (suggest 10MB per file, 5 files max)
- Extracted text from files follows same 30,000 char truncation as website scraping
- Must work with existing LLM provider abstraction (openai/anthropic routing)
- Frontend uses React (no framework change)
- Backend uses FastAPI with Pydantic models

### Business Constraints
- Must improve demo flow for interviews (cleaner, faster setup)
- Must not break existing users who have already completed setup
- SettingsPanel must retain full power-user capabilities

## Assumptions
- Users have sales collateral in PDF/DOCX format they can upload
- File upload goes through the backend (not direct cloud storage)
- Files are processed synchronously (extracted text → LLM) — acceptable for small document sets
- Existing config.json schema can accommodate the new intelligence source type
- The `product_list` capability map mode is sufficient for setup (other modes remain in settings)

## Solution Approaches

### Approach 1: Unified Multi-Source Extraction (Recommended)

**Description**: Add file upload and text paste as new intelligence sources alongside website URL. All three sources feed extracted text into the same LLM extraction prompt. The setup wizard presents them as three radio-button options in Step 1.

**Pros**:
- Minimal changes to extraction pipeline (same prompt, same output)
- Clean UX with clear source selection
- Reuses existing LLM extraction logic
- Easy to add more sources later

**Cons**:
- Only one source per extraction (can't combine website + files)
- File processing is synchronous

**Estimated Complexity**: Medium
**Risk Level**: Low

### Approach 2: Combined Multi-Source Extraction

**Description**: Allow users to provide multiple sources simultaneously (URL + files + text). Combine all extracted text before sending to LLM.

**Pros**:
- Richer intelligence from multiple sources
- More flexible

**Cons**:
- More complex UX (which sources are active?)
- Text combination may exceed LLM context limits
- Harder to attribute which source provided which intelligence
- Over-engineered for the problem

**Estimated Complexity**: High
**Risk Level**: Medium

### Recommended: Approach 1

Approach 1 is simpler, addresses the core problem (enterprise sites block crawlers), and matches the issue description. Users can always re-extract from a different source via SettingsPanel.

## Open Questions

### Critical (Blocks Progress)
- [x] None — the issue description is comprehensive

### Important (Affects Design)
- [ ] Should the paste-text source also be available in SettingsPanel? (Assuming yes, for consistency)
- [ ] Should file uploads be persisted on disk, or just processed and discarded? (Assuming discarded — we keep the extracted intelligence, not the raw files)

### Nice-to-Know (Optimization)
- [ ] Should we support drag-and-drop file upload? (Nice UX but not required for MVP)
- [ ] Should we show extraction progress per file? (Single progress indicator is sufficient)

## Performance Requirements
- **File parsing**: < 5s for typical documents (< 50 pages)
- **LLM extraction**: Same as current (~10-30s depending on provider)
- **File upload**: Accept up to 10MB per file, 5 files max
- **Setup completion**: Total flow should complete in < 2 minutes (excluding LLM wait times)

## Security Considerations
- File uploads must validate MIME type / extension (only PDF, DOCX, PPTX, XLSX, HTML, TXT)
- Uploaded files should be processed in memory or temp directory, then discarded
- No path traversal vulnerabilities in file handling
- Text content is sent to configured LLM provider (same trust model as website scraping)
- No user-uploaded content should be served back via the API

## Test Scenarios

### Functional Tests
1. **Happy path — website URL**: Setup with URL extracts intelligence, generates capability map, auto-links
2. **Happy path — file upload**: Upload PDF, extract intelligence, verify same output structure
3. **Happy path — paste text**: Paste sales content, extract intelligence
4. **403 error handling**: Website returns 403, user sees friendly message with alternatives
5. **File validation**: Reject unsupported file types (e.g., .exe, .zip); accept PDF, DOCX, PPTX, XLSX, HTML, TXT
6. **Empty file**: Upload empty PDF, handle gracefully
7. **Setup completion**: After Step 2, capability map auto-generates and intelligence auto-extracts
8. **SettingsPanel**: File upload works from settings, not just setup wizard

### Non-Functional Tests
1. **Large file**: 10MB PDF processes without timeout
2. **Multiple files**: 5 files combined stay under text limits
3. **Document parser unit tests**: Each format (PDF, DOCX, PPTX, XLSX, HTML, TXT) parses correctly

## Dependencies
- **External Libraries (NEW)**:
  - `pdfplumber` — PDF text extraction
  - `python-docx` — DOCX text extraction
  - `python-pptx` — PPTX text extraction (slides)
  - `openpyxl` — XLSX text extraction (cell values)
- **Internal Systems**:
  - Existing LLM extraction pipeline (seller_intelligence.py)
  - Existing capability map generator (capability_map_generator.py)
  - Existing web crawler (web_crawler.py) — for HTML stripping
- **Existing Libraries**:
  - FastAPI (file upload via `UploadFile`)
  - React (frontend components)

## Risks and Mitigation
| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| PDF extraction quality varies | Medium | Medium | Use pdfplumber (layout-aware); fall back to PyPDF2; truncate to 30k chars |
| Large files cause timeouts | Low | Medium | Enforce 10MB limit; process in streaming fashion |
| Breaking existing setup flow | Low | High | Existing config.json remains compatible; only UI changes |
| File upload CORS/multipart issues | Low | Low | FastAPI handles multipart natively; test with frontend early |

## Notes

### What Changes in the Config Model
- No schema changes needed for SellerIntelligence — the output structure is the same regardless of source
- The source type (url/files/text) is transient — not persisted in config
- Consider adding `last_source_type` field to SellerIntelligence for display purposes (optional)

### Migration / Backward Compatibility
- Users who already completed setup are unaffected — their config.json is unchanged
- The `is_first_run()` check remains the same (company_name empty = first run)
- SettingsPanel gains new capabilities but existing tabs are unchanged

---

## Amendments

<!-- When adding a TICK amendment, add a new entry below this line in chronological order -->

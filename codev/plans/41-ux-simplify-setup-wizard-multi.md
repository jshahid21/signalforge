# Plan: Simplify Setup Wizard + Multi-Source Seller Intelligence

## Metadata
- **ID**: plan-2026-04-12-ux-simplify-setup-wizard-multi
- **Status**: draft
- **Specification**: [codev/specs/41-ux-simplify-setup-wizard-multi.md](../specs/41-ux-simplify-setup-wizard-multi.md)
- **Created**: 2026-04-12

## Executive Summary

Implement Approach 1 (Unified Multi-Source Extraction) from the spec. The work breaks into 5 phases:

1. **Document parser module** — new `backend/tools/document_parser.py` with text extraction for PDF, DOCX, PPTX, XLSX, HTML, TXT
2. **Backend endpoints** — file upload endpoint + text extraction endpoint + 403 error handling
3. **Seller intelligence multi-source** — extend extraction pipeline to accept files and pasted text
4. **Frontend setup wizard** — simplify from 3 steps to 2, add intelligence source selection
5. **Frontend settings panel** — add file upload and paste options to SettingsPanel

## Success Metrics
- [ ] Setup wizard completes in 2 steps (About You + API Keys)
- [ ] Capability map auto-generates from product list after setup
- [ ] Seller intelligence extracts from website URL, uploaded files, or pasted text
- [ ] Intelligence auto-links to capability map after extraction
- [ ] 403 errors show friendly message with alternatives
- [ ] All existing tests pass
- [ ] New backend code has test coverage
- [ ] All 6 file formats parse correctly (PDF, DOCX, PPTX, XLSX, HTML, TXT)

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "document_parser", "title": "Phase 1: Document Parser Module"},
    {"id": "backend_endpoints", "title": "Phase 2: Backend Endpoints"},
    {"id": "seller_intelligence_multi", "title": "Phase 3: Multi-Source Seller Intelligence"},
    {"id": "frontend_wizard", "title": "Phase 4: Setup Wizard Simplification"},
    {"id": "frontend_settings", "title": "Phase 5: Settings Panel Updates"}
  ]
}
```

## Phase Breakdown

### Phase 1: Document Parser Module
**Dependencies**: None

#### Objectives
- Create `backend/tools/document_parser.py` with text extraction for all supported formats
- Add new dependencies to `pyproject.toml`

#### Deliverables
- [ ] `backend/tools/document_parser.py` — parse functions for PDF, DOCX, PPTX, XLSX, HTML, TXT
- [ ] Updated `pyproject.toml` with pdfplumber, python-docx, python-pptx, openpyxl, python-multipart
- [ ] Unit tests for each format in `tests/test_document_parser.py`

#### Implementation Details

**File: `backend/tools/document_parser.py`**

Functions:
- `extract_text_from_file(file_bytes: bytes, filename: str) -> str` — dispatcher by extension
- `_extract_pdf(file_bytes: bytes) -> str` — uses pdfplumber to extract text from all pages
- `_extract_docx(file_bytes: bytes) -> str` — uses python-docx to extract paragraph text
- `_extract_pptx(file_bytes: bytes) -> str` — uses python-pptx to extract text from all slides/shapes
- `_extract_xlsx(file_bytes: bytes) -> str` — uses openpyxl to extract cell values as tab-separated text
- `_extract_html(file_bytes: bytes) -> str` — decodes UTF-8, uses existing `strip_html_tags` from web_crawler.py
- `_extract_txt(file_bytes: bytes) -> str` — decodes UTF-8
- `extract_text_from_files(files: list[tuple[bytes, str]]) -> str` — combines text from multiple files with `\n\n---\n\n` separator, truncates to 30,000 chars

Constants:
- `ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.pptx', '.xlsx', '.html', '.htm', '.txt'}`
- `MAX_FILE_SIZE = 10 * 1024 * 1024` (10MB)
- `MAX_FILES = 5`
- `MAX_COMBINED_TEXT = 30_000`

**File: `pyproject.toml`** — add dependencies:
- `pdfplumber`
- `python-docx`
- `python-pptx`
- `openpyxl`
- `python-multipart`

#### Acceptance Criteria
- [ ] Each format extracts readable text from sample files
- [ ] Unsupported extensions raise ValueError
- [ ] Empty files return empty string (no crash)
- [ ] Combined text truncates at 30,000 chars
- [ ] All unit tests pass

#### Test Plan
- **Unit Tests**: Test each format with small sample files (create test fixtures in `tests/fixtures/`)
- **Edge Cases**: Empty file, oversized file, wrong extension, binary garbage

#### Rollback Strategy
Delete `backend/tools/document_parser.py` and revert `pyproject.toml` changes.

---

### Phase 2: Backend Endpoints
**Dependencies**: Phase 1

#### Objectives
- Add file upload endpoint for seller intelligence extraction
- Add text field to existing extraction endpoint for paste-text source
- Improve 403 error handling with friendly messages

#### Deliverables
- [ ] `POST /settings/seller-intelligence/extract-from-files` endpoint (multipart)
- [ ] Extended `POST /settings/seller-intelligence/extract` with optional `text` field
- [ ] Friendly 403 error messages on extraction failures
- [ ] Tests for new endpoints

#### Implementation Details

**File: `backend/api/routes/settings.py`**

New endpoint — `POST /settings/seller-intelligence/extract-from-files`:
- Accepts `List[UploadFile]` via FastAPI multipart
- Validates file count (max 5), file sizes (max 10MB each), extensions (allowlist)
- Returns 413 for oversized files, 400 for unsupported types
- Calls `document_parser.extract_text_from_files()` to get combined text
- Passes text to `extract_seller_intelligence_from_text()` (new function, Phase 3)
- Returns `{status: "extracted", seller_intelligence: {...}}`

Modified endpoint — `POST /settings/seller-intelligence/extract`:
- Add optional `text` field to `ExtractRequest` body (alongside existing `website_url`)
- If `text` is provided, extract from text directly (skip crawling)
- If `website_url` is provided, use existing crawl logic
- Exactly one of `text` or `website_url` must be provided (validate)

Modified error handling:
- Catch 403/connection errors in the extraction endpoint
- Return 422 with `detail: "Your website blocked our crawler (common for enterprise sites). Try uploading a pitch deck or case study PDF instead."` instead of generic error
- Add specific error code to distinguish scraping failures from other errors

**Request/Response models:**
```python
class ExtractRequest(BaseModel):
    website_url: Optional[str] = None
    text: Optional[str] = None

class ExtractResponse(BaseModel):
    status: str
    seller_intelligence: dict
    source_type: str  # "url", "files", "text"
```

#### Acceptance Criteria
- [ ] File upload endpoint accepts multipart with multiple files
- [ ] File validation rejects wrong types and oversized files
- [ ] Text extraction via paste works through existing endpoint
- [ ] 403 errors return friendly message
- [ ] Tests cover happy path and validation errors

#### Test Plan
- **Unit Tests**: Mock file uploads, test validation, test text extraction path
- **Integration Tests**: End-to-end file upload → extraction flow
- **Error Tests**: 403 simulation, oversized file, wrong extension, both fields provided

#### Rollback Strategy
Revert changes to `settings.py`. Existing endpoints remain functional.

---

### Phase 3: Multi-Source Seller Intelligence
**Dependencies**: Phase 1, Phase 2

#### Objectives
- Extend seller intelligence extraction to accept pre-extracted text (from files or paste)
- Generalize LLM prompt from "website content" to "B2B sales collateral"

#### Deliverables
- [ ] `extract_seller_intelligence_from_text()` function in `seller_intelligence.py`
- [ ] Generalized LLM extraction prompt
- [ ] Updated `extract_and_save_seller_intelligence()` to support text source
- [ ] Tests for text-based extraction

#### Implementation Details

**File: `backend/agents/seller_intelligence.py`**

New function — `extract_seller_intelligence_from_text(text: str, llm_provider: str, llm_model: str) -> SellerIntelligence`:
- Takes pre-extracted text (from documents or paste)
- Uses same LLM extraction logic as `extract_seller_intelligence()`
- Truncates text to 30,000 chars
- Returns SellerIntelligence with `last_scraped` set to current timestamp

Modify LLM prompt (lines 76-114):
- Change "You are analyzing a B2B seller's public website" → "You are analyzing B2B sales collateral (which may include website content, pitch decks, case studies, battlecards, or other sales materials)"
- Change "Website content:" → "Content:"
- This is the same prompt used by both URL and text extraction paths

Modify `extract_and_save_seller_intelligence()`:
- Add optional `text: str` parameter
- If `text` is provided, call `extract_seller_intelligence_from_text()` instead of crawling
- Auto-link to capability map remains the same

#### Acceptance Criteria
- [ ] Text extraction produces same SellerIntelligence structure as URL extraction
- [ ] Existing URL extraction still works unchanged
- [ ] Generalized prompt works for both website and document content
- [ ] Auto-link to capability map works regardless of source

#### Test Plan
- **Unit Tests**: Test `extract_seller_intelligence_from_text()` with sample sales content
- **Integration Tests**: Text → LLM → SellerIntelligence → auto-link flow

#### Rollback Strategy
Revert `seller_intelligence.py` changes. URL extraction continues working.

---

### Phase 4: Setup Wizard Simplification
**Dependencies**: Phase 2, Phase 3

#### Objectives
- Simplify SetupWizard from 3 steps to 2
- Add intelligence source selection (URL, file upload, paste text)
- Auto-generate capability map + extract intelligence after Step 2

#### Deliverables
- [ ] Simplified SetupWizard.tsx with 2 steps
- [ ] Intelligence source radio buttons with conditional inputs
- [ ] Sequential post-setup orchestration (cap map → extract → auto-link)
- [ ] Updated API client with new endpoint calls

#### Implementation Details

**File: `frontend/src/components/SetupWizard.tsx`**

Step changes:
- Remove Step 3 (Capability Map) entirely
- Remove `portfolioSummary` field from Step 1
- Remove `genMode` state and capability map generation modes
- Step types: `'about-you' | 'api-keys'`

Step 1 — About You:
- Company Name (required, existing)
- Products / Services (multiline textarea, existing as `portfolioItems`)
- Intelligence source radio: `'none' | 'url' | 'files' | 'text'`
  - `url`: Website URL input (existing)
  - `files`: File input with `accept=".pdf,.docx,.pptx,.xlsx,.html,.htm,.txt"` and `multiple`
  - `text`: Textarea for pasting content
  - `none`: No source selected (default)
- Save handler: calls `settingsApi.putSellerProfile()` with company name + products, stores intelligence source choice in component state

Step 2 — API Keys:
- Same fields as current (jsearch, tavily, llm_provider, llm_model)
- After save, orchestrate sequentially:
  1. `settingsApi.generateCapabilityMap({ product_list: portfolioItems })`
  2. If intelligence source is `url`: `settingsApi.extractSellerIntelligence({ website_url })`
  3. If intelligence source is `files`: `settingsApi.extractFromFiles(files)`
  4. If intelligence source is `text`: `settingsApi.extractSellerIntelligence({ text })`
  5. `settingsApi.autoLinkIntelligence()` (only if extraction succeeded)
  6. `setupApi.saveConfig({})` to mark complete
- Show loading spinner with status messages during orchestration
- Handle 403/extraction errors as soft failures (complete setup, show message)

**File: `frontend/src/api/client.ts`**

Add new method:
- `extractFromFiles(files: File[]): Promise<any>` — POST multipart to `/settings/seller-intelligence/extract-from-files`

Modify existing method:
- `extractSellerIntelligence(data)` — accept `{ website_url?: string, text?: string }`

#### Acceptance Criteria
- [ ] Wizard shows 2 steps with correct step indicator
- [ ] All three intelligence sources work (URL, files, paste)
- [ ] No intelligence source is a valid option (skip extraction)
- [ ] Capability map auto-generates from products after Step 2
- [ ] Auto-link runs after extraction completes
- [ ] 403 errors show friendly message, setup still completes
- [ ] Loading states shown during post-setup orchestration

#### Test Plan
- **Manual Testing**: Complete setup with each intelligence source; test with no source; test 403 scenario
- **Edge Cases**: Empty products list, no files selected, empty paste text

#### Rollback Strategy
Revert SetupWizard.tsx and client.ts. Old 3-step wizard restores.

---

### Phase 5: Settings Panel Updates
**Dependencies**: Phase 2, Phase 3

#### Objectives
- Add file upload and paste text options to SettingsPanel Seller Profile tab
- Preserve all existing editing capabilities

#### Deliverables
- [ ] File upload option in Seller Profile tab
- [ ] Paste text option in Seller Profile tab
- [ ] Source selection (URL / files / text) for re-extraction

#### Implementation Details

**File: `frontend/src/components/SettingsPanel.tsx`**

Modify SellerProfileTab (lines 31-189):
- Add intelligence source radio: `'url' | 'files' | 'text'`
- `url`: Keep existing website URL + "Re-scrape" button
- `files`: File input with same accept/multiple as wizard + "Extract from Files" button
- `text`: Textarea + "Extract from Text" button
- Each extraction option calls the appropriate endpoint
- On success, update `intelligence` state with new data
- On failure, show error message (reuse existing `extractError` state)
- Existing inline intelligence editor remains unchanged

#### Acceptance Criteria
- [ ] All three source options available in SettingsPanel
- [ ] Re-scrape from URL still works
- [ ] File upload from settings extracts intelligence
- [ ] Paste text from settings extracts intelligence
- [ ] Intelligence editor still works after re-extraction
- [ ] Auto-link available after re-extraction

#### Test Plan
- **Manual Testing**: Re-extract using each source from SettingsPanel
- **Edge Cases**: Switch sources, extract with no capability map

#### Rollback Strategy
Revert SettingsPanel.tsx changes. Existing tab functionality restored.

---

## Dependency Map
```
Phase 1 (Document Parser) ──→ Phase 2 (Backend Endpoints) ──→ Phase 3 (Multi-Source Intelligence)
                                                                        │
                                                                        ├──→ Phase 4 (Setup Wizard)
                                                                        │
                                                                        └──→ Phase 5 (Settings Panel)
```

Phases 4 and 5 are independent of each other and can be implemented in either order.

## Resource Requirements
### Development Resources
- **Environment**: Python 3.10+, Node.js, pdfplumber/python-docx/python-pptx/openpyxl installed

### Infrastructure
- No database changes
- No new services
- Config file format unchanged
- New Python dependencies in pyproject.toml

## Risk Analysis
### Technical Risks
| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| PDF extraction quality varies | Medium | Medium | Use pdfplumber (layout-aware); truncate to 30k chars |
| python-multipart not installed | Low | High | Add to pyproject.toml in Phase 1 |
| Large file upload timeout | Low | Medium | 10MB limit enforced; FastAPI handles streaming |
| Multipart CORS issues | Low | Low | FastAPI handles multipart natively |

## Validation Checkpoints
1. **After Phase 1**: Run `pytest tests/test_document_parser.py` — all formats parse correctly
2. **After Phase 2**: Run endpoint tests — file upload and text extraction work
3. **After Phase 3**: Run intelligence extraction with text input — same output structure
4. **After Phase 4**: Manual test full setup flow with each source type
5. **After Phase 5**: Manual test settings panel with each source type

## Notes
- The `last_scraped` field name is kept for backward compatibility but now applies to all source types
- Files are processed in memory and discarded — not persisted to disk
- The 30,000 char truncation matches existing website scraping behavior
- `product_list` is the only capability map generation mode used in the wizard; other modes stay in SettingsPanel

---

## Amendment History

<!-- When adding a TICK amendment, add a new entry below this line in chronological order -->

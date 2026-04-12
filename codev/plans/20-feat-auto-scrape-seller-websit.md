# Plan: Auto-Scrape Seller Website for Differentiators and Sales Plays

## Metadata
- **ID**: plan-2026-04-12-auto-scrape-seller-website
- **Status**: draft
- **Specification**: codev/specs/20-feat-auto-scrape-seller-websit.md
- **Created**: 2026-04-12

## Executive Summary

Implements the LLM-powered website intelligence extraction approach (Approach 1 from spec). The work is broken into 4 phases that build incrementally: data models and config first, then the extraction agent, then draft enrichment, and finally frontend integration. Each phase is independently testable and committable.

## Success Metrics
- [ ] All specification success criteria met
- [ ] Test coverage for new code
- [ ] Existing tests continue to pass
- [ ] Graceful fallback when no website URL or intelligence available
- [ ] Draft quality improvement verified through test scenarios

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "data_models", "title": "Phase 1: Data Models and Config"},
    {"id": "extraction_agent", "title": "Phase 2: Seller Intelligence Extraction Agent"},
    {"id": "draft_enrichment", "title": "Phase 3: Draft Enrichment"},
    {"id": "frontend", "title": "Phase 4: Frontend Integration"}
  ]
}
```

## Phase Breakdown

### Phase 1: Data Models and Config
**Dependencies**: None

#### Objectives
- Extend seller profile data models to include `website_url` and structured `seller_intelligence`
- Add `extract_links` function to `web_crawler.py` for subpage discovery
- Ensure backward compatibility — existing configs without website_url/intelligence still load correctly

#### Deliverables
- [ ] `SellerIntelligence` Pydantic model with four intelligence categories
- [ ] Updated `SellerProfileConfig` with `website_url` and `seller_intelligence` fields
- [ ] Updated `SellerProfile` TypedDict with matching fields
- [ ] `extract_links()` function in `web_crawler.py`
- [ ] API endpoint updates for seller profile (GET/PUT) to include new fields
- [ ] Unit tests for all new models, config loading, and link extraction

#### Implementation Details

**New Pydantic models** in `backend/config/loader.py`:
```python
class SalesPlay(BaseModel):
    """A use case / value proposition mapped to a problem category."""
    play: str           # e.g., "FinOps cost optimization"
    category: str       # e.g., "cost_optimization"

class ProofPoint(BaseModel):
    """Customer evidence — logos, case studies, metrics."""
    customer: str       # e.g., "Acme Corp"
    summary: str        # e.g., "Reduced cloud spend by 40%"

class SellerIntelligence(BaseModel):
    """Structured intelligence extracted from seller's website."""
    differentiators: list[str] = []          # What makes the product unique
    sales_plays: list[SalesPlay] = []        # Use cases by problem category
    proof_points: list[ProofPoint] = []      # Customer evidence
    competitive_positioning: list[str] = []  # How seller differentiates vs alternatives
    last_scraped: str | None = None          # ISO timestamp of last extraction
```

**Updated `SellerProfileConfig`**:
- Add `website_url: str | None = None`
- Add `seller_intelligence: SellerIntelligence = SellerIntelligence()`

**Updated `SellerProfile` TypedDict** in `backend/models/state.py`:
- Add `website_url: str` (optional)
- Add `seller_intelligence: dict` (serialized SellerIntelligence)

**`extract_links()` in `backend/tools/web_crawler.py`**:
- Parse `<a href>` tags from raw HTML *before* tag stripping
- Filter to same-domain links matching key patterns: `/product`, `/solutions`, `/platform`, `/customers`, `/case-stud`, `/about`, `/why-`
- Return deduplicated list of absolute URLs (max 9)

**API route updates** in `backend/api/routes/settings.py`:
- `GET /settings/seller-profile`: Include `website_url` and `seller_intelligence` in response
- `PUT /settings/seller-profile`: Accept `website_url` in update payload
- Seller intelligence is read-only via the profile endpoint (updated via extraction endpoint in Phase 2)

#### Acceptance Criteria
- [ ] Config loads correctly with and without `website_url`/`seller_intelligence` (backward compat)
- [ ] `extract_links()` correctly parses links from sample HTML
- [ ] `extract_links()` filters to same-domain, key-pattern matches only
- [ ] API endpoints return and accept the new fields
- [ ] All existing tests pass

#### Test Plan
- **Unit Tests**: SellerIntelligence model validation, SellerProfileConfig serialization/deserialization, `extract_links()` with various HTML samples, backward compatibility with old config format
- **Integration Tests**: API endpoint round-trip for seller profile with new fields

#### Rollback Strategy
Revert the commit — no data migration needed since new fields have defaults.

#### Risks
- **Risk**: Old config files without new fields could fail to load
  - **Mitigation**: All new fields have defaults (None or empty model)

---

### Phase 2: Seller Intelligence Extraction Agent
**Dependencies**: Phase 1

#### Objectives
- Create an agent that crawls a seller's website and extracts structured intelligence using LLM
- Add API endpoint to trigger extraction
- Handle errors gracefully (unreachable sites, LLM failures)

#### Deliverables
- [ ] `backend/agents/seller_intelligence.py` — extraction agent
- [ ] `POST /settings/seller-intelligence/extract` API endpoint
- [ ] Unit tests for extraction logic (mocked HTTP + LLM)
- [ ] Integration test for the extraction pipeline

#### Implementation Details

**`backend/agents/seller_intelligence.py`**:

Core functions:
1. `extract_seller_intelligence(website_url: str, llm_provider: str, llm_model: str) -> SellerIntelligence`
   - Validate URL (HTTPS required)
   - Crawl homepage with `crawl_url()`
   - Extract links with `extract_links()` from raw HTML
   - Crawl up to 9 discovered subpages (with 1s delay between requests)
   - Combine all page text (truncate to ~30K chars to fit LLM context)
   - Call LLM with structured output prompt to extract SellerIntelligence
   - Set `last_scraped` timestamp
   - Return SellerIntelligence

2. `_build_extraction_prompt(combined_text: str) -> str`
   - System prompt instructing LLM to extract four categories from website content
   - JSON output schema matching SellerIntelligence model
   - Instructions to leave categories empty if no evidence found (no hallucination)

**Error handling**:
- URL validation failure → raise `ValueError` with clear message
- HTTP fetch failure → log warning, continue with pages that succeeded
- Zero pages fetched → raise descriptive error
- LLM call failure → raise descriptive error (caller handles fallback)

**API endpoint** in `backend/api/routes/settings.py`:
- `POST /settings/seller-intelligence/extract`
  - Request body: `{ "website_url": "https://..." }` (optional — falls back to config's `website_url`)
  - Runs extraction, saves result to config
  - Returns extracted SellerIntelligence
  - Returns appropriate HTTP error on failure

#### Acceptance Criteria
- [ ] Extraction produces structured output for a real website
- [ ] HTTPS-only validation works (HTTP rejected)
- [ ] Partial crawl failures don't crash the agent
- [ ] LLM failure returns clear error
- [ ] Extracted intelligence is saved to config
- [ ] `last_scraped` timestamp is set

#### Test Plan
- **Unit Tests**: URL validation, `_build_extraction_prompt()` output, LLM response parsing, error handling for each failure mode
- **Integration Tests**: Full extraction pipeline with mocked HTTP responses and mocked LLM (verifying the SellerIntelligence output structure)

#### Rollback Strategy
Revert commit — new file with no impact on existing functionality.

#### Risks
- **Risk**: LLM produces malformed JSON output
  - **Mitigation**: Use structured output / JSON mode if available; fallback to regex extraction; retry once

---

### Phase 3: Draft Enrichment
**Dependencies**: Phase 2

#### Objectives
- Inject seller intelligence into draft generation prompts
- Match sales plays to signal categories
- Select relevant differentiators based on persona/signal context
- Maintain graceful fallback for empty intelligence

#### Deliverables
- [ ] Updated `_build_draft_system_prompt()` in `backend/agents/draft.py`
- [ ] Intelligence selection logic (matching plays to signals, differentiators to pain points)
- [ ] Unit tests for enriched prompt generation
- [ ] Integration test verifying draft quality with and without intelligence

#### Implementation Details

**Updated `_build_draft_system_prompt()` in `backend/agents/draft.py`**:
- If `seller_intelligence` is present and non-empty:
  - Inject a `## Seller Intelligence` section into the system prompt
  - Include top 2-3 differentiators most relevant to the signal context
  - Include the sales play matching the signal category (if any)
  - Include 1-2 proof points relevant to the persona's industry/role
  - Include competitive positioning summary
  - Instruction: "Reference specific differentiators and proof points where relevant to the prospect's situation. Do not list all of them — pick the 1-2 most compelling for this specific persona."
- If `seller_intelligence` is empty/None:
  - Existing behavior unchanged (portfolio_items only)

**Sales play matching logic**:
- Map signal types/categories to sales play categories
- Example mappings:
  - Signal mentions "cost", "budget", "spend" → match `cost_optimization` plays
  - Signal mentions "security", "compliance", "risk" → match `security_compliance` plays
  - Signal mentions "scale", "performance", "infrastructure" → match `platform_scaling` plays
- Matching done via keyword overlap between signal content and play categories
- If no match, include the highest-priority play as a general fallback

**Proof point selection**:
- Prefer proof points from companies in the same industry as the prospect
- Fallback to any proof point with quantified metrics

#### Acceptance Criteria
- [ ] Drafts with intelligence include relevant differentiators
- [ ] Sales plays match signal categories correctly
- [ ] Drafts without intelligence use existing fallback behavior
- [ ] No forced mentions — intelligence is only included when relevant
- [ ] Prompt stays within reasonable token limits

#### Test Plan
- **Unit Tests**: `_build_draft_system_prompt()` with various intelligence/signal combinations, sales play matching logic, proof point selection, empty intelligence fallback
- **Integration Tests**: End-to-end draft generation with mocked LLM comparing output with and without seller intelligence

#### Rollback Strategy
Revert commit — draft.py changes are isolated to the system prompt builder.

#### Risks
- **Risk**: Seller intelligence makes prompts too long, increasing cost/latency
  - **Mitigation**: Cap intelligence injection at ~500 tokens; select only most relevant items

---

### Phase 4: Frontend Integration
**Dependencies**: Phase 1, Phase 2

#### Objectives
- Add website URL field to Setup Wizard
- Add seller intelligence view/edit to Settings Panel
- Show extraction loading state and re-scrape button
- Handle errors gracefully in the UI

#### Deliverables
- [ ] Updated `frontend/src/components/SetupWizard.tsx` — website URL field in Step 1
- [ ] Updated `frontend/src/components/SettingsPanel.tsx` — seller intelligence tab/section
- [ ] Frontend API client updates for new endpoints
- [ ] Loading/progress state for extraction
- [ ] Tests for new UI components

#### Implementation Details

**SetupWizard.tsx changes**:
- Add `website_url` input field in Step 1 (Seller Profile step), below portfolio items
- Label: "Company Website URL (optional)"
- Placeholder: "https://www.yourcompany.com"
- HTTPS validation (show error if HTTP)
- On "Next" click: save website_url with seller profile, then trigger extraction in background
- Show a loading indicator: "Extracting seller intelligence from website..." with a spinner
- Allow user to skip/proceed if extraction takes too long (non-blocking)

**SettingsPanel.tsx changes**:
- Add "Seller Intelligence" section within the existing Seller Profile tab (or as a new sub-section)
- Display each intelligence category:
  - **Differentiators**: Editable list of strings
  - **Sales Plays**: Editable list with play + category fields
  - **Proof Points**: Editable list with customer + summary fields
  - **Competitive Positioning**: Editable list of strings
- Show `last_scraped` timestamp
- "Re-scrape Website" button that triggers `POST /settings/seller-intelligence/extract`
- Loading state during re-scrape
- Error display if extraction fails

**Frontend API client updates**:
- Add `extractSellerIntelligence(websiteUrl?: string)` to settings API client
- Update `putSellerProfile()` to include `website_url`
- Update `getSellerProfile()` response type to include new fields

#### Acceptance Criteria
- [ ] Website URL field appears in Setup Wizard
- [ ] Extraction runs with loading state after setup
- [ ] Seller intelligence is viewable and editable in Settings
- [ ] Re-scrape button works
- [ ] Error states display clearly
- [ ] Skipping website URL still works (no regression)

#### Test Plan
- **Unit Tests**: Component rendering with/without intelligence data, form validation (HTTPS), loading states
- **Integration Tests**: Setup flow end-to-end, settings panel edit and save round-trip

#### Rollback Strategy
Revert commit — frontend changes are isolated to two component files and the API client.

#### Risks
- **Risk**: 60-second extraction blocks setup wizard UX
  - **Mitigation**: Run extraction asynchronously; allow skipping; show clear progress indicator

---

## Dependency Map
```
Phase 1 (Data Models) ──→ Phase 2 (Extraction Agent) ──→ Phase 3 (Draft Enrichment)
         │
         └──────────────→ Phase 4 (Frontend Integration)
```

Phase 3 and Phase 4 can theoretically proceed in parallel after Phase 2, but will be done sequentially for simplicity.

## Resource Requirements
### Development Resources
- **Engineers**: 1 AI builder (full-stack: Python backend + React frontend)
- **Environment**: Local dev with configured LLM provider

### Infrastructure
- No database changes (config file based)
- No new services
- New config fields added to `~/.signalforge/config.json`
- No monitoring additions needed for v1

## Integration Points
### External Systems
- **System**: Seller's public website
  - **Integration Type**: HTTP/HTTPS crawling
  - **Phase**: Phase 2
  - **Fallback**: Manual entry via Settings Panel

### Internal Systems
- **web_crawler.py**: Extended with `extract_links()` in Phase 1
- **draft.py**: Modified system prompt in Phase 3
- **config/loader.py**: Extended models in Phase 1
- **settings API routes**: Extended in Phase 1 and Phase 2

## Risk Analysis
### Technical Risks
| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| web_crawler.py can't extract links from some sites | Medium | Low | Best-effort link discovery; crawl homepage-only fallback | Builder |
| LLM produces malformed extraction output | Low | Medium | Structured output mode; retry once; validation | Builder |
| Draft prompt exceeds token limit with intelligence | Low | Medium | Cap intelligence injection at ~500 tokens | Builder |

## Validation Checkpoints
1. **After Phase 1**: Config loads correctly with new fields; `extract_links()` works on sample HTML; API returns new fields
2. **After Phase 2**: Extraction agent produces valid SellerIntelligence from a real URL; errors handled gracefully
3. **After Phase 3**: Drafts reference differentiators when intelligence is available; fallback works when empty
4. **After Phase 4**: Full user flow works end-to-end in browser

## Documentation Updates Required
- [ ] API documentation (new endpoint, updated response schemas)
- [ ] Architecture docs (`codev/resources/arch.md`)

## Post-Implementation Tasks
- [ ] End-to-end manual testing of full flow
- [ ] Verify no regressions in existing pipeline

## Expert Review
<!-- Porch will run 3-way consultation automatically -->

## Approval
- [ ] Technical Lead Review
- [ ] Engineering Manager Approval
- [ ] Resource Allocation Confirmed
- [ ] Expert AI Consultation Complete

## Change Log
| Date | Change | Reason | Author |
|------|--------|--------|--------|
| 2026-04-12 | Initial plan | Created from spec | Builder |

## Notes

The phase structure mirrors the spec's two-phase description (Phase 1: Seller Intelligence Extraction, Phase 2: Draft Enrichment) but breaks them into finer-grained implementation phases for better atomic commits and independent testability. The data model phase is separated out because it's a prerequisite for both the backend agent and frontend work.

---

## Amendment History

<!-- When adding a TICK amendment, add a new entry below this line in chronological order -->

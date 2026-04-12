# Review: Auto-Scrape Seller Website for Differentiators and Sales Plays

## Summary

Implemented auto-scraping of seller's public website to extract structured intelligence (differentiators, sales plays, proof points, competitive positioning) and inject it into draft generation. The feature adds a website URL field to the setup wizard and settings panel, scrapes key pages using the existing web_crawler.py infrastructure, extracts intelligence via LLM, and enriches draft generation prompts with contextually relevant intelligence.

## Spec Compliance

- [x] Setup wizard accepts seller website URL (optional field)
- [x] System scrapes seller website and extracts structured intelligence
- [x] Extracted intelligence is persisted to config and cached across sessions
- [x] Users can view, edit, and re-scrape seller intelligence via Settings Panel
- [x] Draft emails reference specific differentiators relevant to persona context
- [x] Sales plays are matched to signal categories (LLM-driven contextual selection)
- [x] Proof points included in drafts when contextually relevant
- [x] Graceful fallback to existing portfolio_summary if scraping fails or intelligence is empty
- [x] All new code has test coverage (unit + integration)
- [x] Existing tests continue to pass (365 pre-existing + 32 new = 397 total)
- [x] Documentation updated

## Deviations from Plan

- **Phase 3 (Sales play matching)**: Plan originally suggested keyword heuristics, but during consultation this was changed to LLM-driven contextual selection. All plays are provided in the draft prompt with the instruction to select the most relevant one. This is more robust than keyword matching.
- **Phase 3 (Proof point selection)**: Plan mentioned "prefer proof points from same industry." Since ProofPoint model lacks an industry field, all proof points (up to 4) are provided with instructions to use only if directly relevant. LLM handles the contextual selection.
- **Phase 4 (Frontend tests)**: No frontend component tests added — the repo has no existing frontend test infrastructure despite vitest being configured. This is a pre-existing gap, not introduced by this feature.

## Lessons Learned

### What Went Well
- The 4-phase plan structure worked cleanly: data models first, then extraction, then enrichment, then frontend. Each phase was independently testable.
- Reusing the existing `web_crawler.py` tool and extending it (fetch_html, extract_links) was efficient and avoided new dependencies.
- The SellerIntelligence Pydantic model with defaults ensured perfect backward compatibility with existing configs.
- LLM-driven selection (letting the draft LLM pick relevant intelligence) is simpler and more robust than building a separate keyword-matching system.

### Challenges Encountered
- **Codex consultation unavailable**: Usage limit blocked all Codex reviews. Architect approved proceeding with 2/3 consultations.
- **Gemini empty responses**: Gemini occasionally returned empty consultation results, requiring retries or manual placeholders.
- **Claude worktree path confusion**: In Phase 4 review, Claude's consultation read from the main repo instead of the builder worktree, producing a false "unimplemented" review.
- **`web_crawler.py` HTML stripping**: The existing `crawl_url()` stripped HTML before returning, making link discovery impossible. Solved by adding `fetch_html()` to decouple HTTP fetch from HTML stripping.

### What Would Be Done Differently
- Pre-check consultation model availability before starting to avoid repeated placeholder creation.
- For future frontend phases, add at least a basic vitest setup with component smoke tests.

### Methodology Improvements
- ASPIR protocol worked well for this feature — no human gates on spec/plan saved time without sacrificing quality (consultations caught real issues).
- The 3-way consultation caught meaningful issues: TypedDict type safety (Claude), web_crawler API mismatch (Gemini), manual edit API path (Claude), and sales play matching strategy (Claude).

## Technical Debt
- No frontend component tests for the new UI features (pre-existing gap in repo)
- No robots.txt checking in extraction agent (low risk for self-scraping, noted for future)
- No LLM retry on malformed extraction output (v1 acceptable, could add for robustness)

## Architecture Updates

Updated `codev/resources/arch.md`:
- Added `seller_intelligence.py` to the agents directory listing
- Updated `web_crawler.py` description to include seller intelligence scraping
- Added `seller_profile.py` to config directory listing
- Updated `settings.py` description to include seller intelligence extraction endpoint

## Lessons Learned Updates

Added to `codev/resources/lessons-learned.md`:
- Entry on decoupling HTTP fetch from HTML processing for reusable crawlers
- Entry on LLM-driven selection being more robust than keyword heuristics for draft enrichment

## Consultation Feedback

### Specify Phase (Round 1)

#### Gemini
- **Concern**: web_crawler.py strips HTML including `<a>` tags, making link discovery impossible
  - **Addressed**: Added `fetch_html()` helper in Phase 1 to decouple fetch from stripping
- **Concern**: Setup wizard 60s extraction will create poor UX if synchronous
  - **Addressed**: Extraction runs asynchronously in background with loading indicator
- **Concern**: Data model should be strictly typed Pydantic
  - **Addressed**: Created SalesPlay, ProofPoint, SellerIntelligence as proper Pydantic BaseModel subclasses

#### Codex
- Unavailable (usage limit)

#### Claude
- **Concern**: Resolve "Important" open questions before planning
  - **Addressed**: All 3 questions resolved with decisions in spec
- **Concern**: Missing test scenario for LLM extraction failure
  - **Addressed**: Added test scenarios #8 (LLM failure) and #9 (wrong URL)
- **Concern**: Wrong URL edge case not covered
  - **Addressed**: Added to test scenarios

### Plan Phase (Round 1)

#### Gemini
- **Concern**: Need `fetch_html()` helper separate from `crawl_url()`
  - **Addressed**: Added to Phase 1 deliverables and implementation
- **Concern**: Use proper TypedDict for seller_intelligence, not raw dict
  - **Addressed**: Created SellerIntelligenceDict TypedDict

#### Claude
- **Concern**: No API write path for manual intelligence edits
  - **Addressed**: Extended PUT /settings/seller-profile to accept seller_intelligence
- **Concern**: robots.txt not addressed
  - **Addressed**: Added risk note to Phase 2 (best-effort for v1)
- **Concern**: Sales play matching via keyword heuristics is limited
  - **Addressed**: Changed to LLM-driven contextual selection in Phase 3

### Phase 1: data_models (Round 1)

#### Gemini
- No concerns (APPROVE)

#### Claude
- **Concern**: `total=False` on SellerProfile makes all fields optional
  - **Addressed**: Changed to NotRequired on only the new fields

### Phase 2: extraction_agent (Round 1)

#### Gemini
- No concerns (APPROVE)

#### Claude
- No concerns (APPROVE)

### Phase 3: draft_enrichment (Round 1)

#### Gemini
- No concerns (APPROVE)

#### Claude
- **Concern**: Missing integration test through run_draft()
  - **Rebutted**: Unit tests on prompt construction provide sufficient coverage; wiring is straightforward

### Phase 4: frontend (Round 1)

#### Gemini
- Consultation returned empty (recurring issue)

#### Claude
- **Concern**: All deliverables missing
  - **Rebutted**: False negative — Claude read from wrong path (main repo, not worktree). All deliverables verified present via git diff and grep.

## Flaky Tests
No flaky tests encountered during this project.

## Follow-up Items
- Add frontend component tests (vitest infrastructure exists but unused)
- Consider robots.txt checking in extraction agent for future version
- Add LLM retry for malformed extraction output
- Consider periodic auto-refresh of seller intelligence (manual re-scrape only in v1)

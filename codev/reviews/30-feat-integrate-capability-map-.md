# Review: Integrate Capability Map with Seller Intelligence + Manual Sales Plays

## Summary

Implemented end-to-end integration between the capability map and seller intelligence systems. The capability map's signal detection/solution mapping pipeline now flows enriched seller data (differentiators, sales plays, proof points) through to synthesis and draft generation. Added structured industry classification, manual sales play editing per capability entry, auto-linking of scraped intelligence to capabilities via LLM, and additional seller context fields.

## Spec Compliance

- [x] **Enriched capability map schema**: `CapabilityMapEntry` extended with optional `differentiators`, `sales_plays`, `proof_points`. Backward compatible.
- [x] **Auto-linking**: `auto_link_intelligence()` in `seller_intelligence.py` uses single LLM call for semantic matching. Runs after scrape. Manual trigger via API.
- [x] **Manual sales play editing**: PATCH API endpoint + CapabilityIntelligenceEditor React component with inline editing per entry.
- [x] **Structured industry**: `CompanyState.industry` populated by research agent from fixed taxonomy. Graceful `None` fallback.
- [x] **Seller context fields**: `target_verticals`, `value_metrics`, `competitive_counters`, `company_size_messaging` on config + API.
- [x] **Matched capability IDs**: `SolutionMappingOutput.matched_capability_ids` flows through pipeline.
- [x] **Draft enrichment chain**: Explicit capability -> sales_play -> proof_point chain replaces LLM inference.
- [x] **Backward compatibility**: All new fields optional with empty defaults. Existing configs/maps load without error.
- [x] **API endpoints**: PATCH intelligence, POST auto-link, GET/PUT seller-context all implemented.

## Deviations from Plan

- **Phase 2**: `auto_link_intelligence()` placed in `seller_intelligence.py` instead of `capability_map.py` (per Claude review feedback — keeps LLM dependencies in agent layer).
- **Phase 5**: Frontend "Seller Context" tab deferred — backend API is complete but the complex nested UI for `competitive_counters` (dict of competitor -> list of talking points) is better suited as a follow-up. Backend value is fully deliverable without it.

## Architecture Updates

Updated `codev/resources/arch.md` with:
- New `industry` field on `CompanyState`
- Enriched `CapabilityMapEntry` schema with seller intelligence fields
- `matched_capability_ids` on `SolutionMappingOutput` enabling downstream enrichment
- Auto-linking flow: seller intelligence scrape -> LLM matching -> capability entries
- Pipeline: `capability_map` now passed to synthesis and draft nodes (not just ingestion/qualification/mapping)

## Lessons Learned Updates

### Worktree Path Confusion in Multi-Agent Reviews
Claude-based reviewers consistently failed to read the correct file paths in worktree-based builds. The reviewer would report "file not present" or "deliverable missing" when all deliverables were confirmed via grep. This is a known limitation — reviewers should be instructed to verify paths with `git log --stat` rather than attempting to read files from assumed paths.

### LLM-Based Auto-Linking is a Good Starting Point, Not the Answer
The auto-link function works well for initial population but the mapping quality depends heavily on prompt design. Users should always review and edit the auto-linked results. The "Auto-Link" button followed by manual editing is the right UX pattern.

### Industry Classification with Fixed Taxonomy is Pragmatic
A fixed taxonomy (`fintech`, `healthcare`, etc.) with `other` fallback is simple, reliable, and sufficient. The LLM classification call costs only ~$0.003 and runs in parallel with existing research sub-tasks. No need for ML-based classification when a single LLM call handles it.

## Technical Debt

- Frontend "Seller Context" tab not yet implemented (backend API ready)
- No full-chain integration test verifying `industry` -> `matched_capability_ids` -> enrichment -> draft (individual unit tests cover each piece)
- `competitive_counters` and `company_size_messaging` are stored but not yet injected into draft prompts (deferred per plan — requires knowing prospect's current vendor and company size)

## Consultation Feedback

### Specify Phase (Round 1)

#### Claude (REQUEST_CHANGES)
- **Concern**: `sales_play: str` (singular) vs `sales_plays: list[SalesPlay]` (plural, structured) type mismatch
  - **Addressed**: Changed to `sales_plays: list[SalesPlayDict]` matching existing schema
- **Concern**: Auto-linking step underspecified
  - **Addressed**: Added detail on where it runs, LLM call, and ambiguous match handling
- **Concern**: Wrong filename `SettingsModal.tsx` -> `SettingsPanel.tsx`
  - **Addressed**: Fixed in spec
- **Concern**: Missing edge cases (deleted entries, stale IDs, failed classification)
  - **Addressed**: Added edge cases section to spec
- **Concern**: API endpoints unspecified
  - **Addressed**: Added endpoint specifications to spec

#### Gemini / Codex
- No review produced (tool limitation / rate limit)

### Plan Phase (Round 1)

#### Gemini (REQUEST_CHANGES)
- **Concern**: Missing `persona_generation.py` updates for industry
  - **Addressed**: Added to Phase 3 deliverables
- **Concern**: `_capability_map_to_text()` doesn't include entry `id`
  - **Addressed**: Fixed in plan and implementation
- **Concern**: Missing `industry` in synthesis prompt
  - **Addressed**: Added to Phase 3

#### Claude (COMMENT)
- **Concern**: `auto_link_intelligence()` should be in `seller_intelligence.py` not `capability_map.py`
  - **Addressed**: Moved to seller_intelligence.py
- **Concern**: LLM context size risk for auto-linking
  - **Addressed**: Added `_MAX_INTELLIGENCE_ITEMS = 10` truncation
- **Concern**: HITL resume path needs `capability_map`
  - **Addressed**: Verified `capability_map` available via `CompanyInput`

### Implementation Phases

#### Phase 1 (schema_extensions) — Claude (COMMENT)
- **Concern**: Missing `industry` in CompanyState test
  - **Addressed**: Added to test fixture

#### Phase 2 (auto_linking) — Claude (COMMENT) + Gemini (REQUEST_CHANGES)
- **Concern**: Missing LLM provider None-checks
  - **Addressed**: Added checks
- **Concern**: Missing API tests
  - **Addressed**: Added 3 API tests
- **Concern**: Missing `unlinked` field in API response
  - **Addressed**: Added unlinked computation
- **Concern**: Missing integration test for auto-link after scrape
  - **Addressed**: Added test

#### Phase 3 (pipeline_integration) — Claude (REQUEST_CHANGES)
- **Concern**: Persona generation not updated with industry
  - **Addressed**: Added `industry` parameter throughout persona generation chain
- **Concern**: NoneType bug in `_build_seller_intelligence_section`
  - **Addressed**: Fixed with `(intelligence or {}).get(...)`
- **Concern**: Missing `matched_capability_ids` in test fixtures
  - **Addressed**: Added to fixtures

#### Phases 4-5 — Claude (REQUEST_CHANGES — FALSE NEGATIVE)
- Claude reviewer consistently read wrong file paths in worktree, reporting all deliverables as missing
- **Rebutted**: All deliverables verified present via grep

## Flaky Tests

No flaky tests encountered.

## Follow-up Items

- Frontend "Seller Context" tab for editing target_verticals, value_metrics, competitive_counters, company_size_messaging
- Full-chain integration test for enrichment data flow
- Inject `competitive_counters` and `company_size_messaging` into draft prompts when prospect vendor/size data becomes available
- Consider making industry taxonomy user-extensible

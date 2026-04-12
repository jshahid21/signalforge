# Plan: Integrate Capability Map with Seller Intelligence + Manual Sales Plays

## Metadata
- **ID**: plan-2026-04-12-integrate-capability-map
- **Status**: draft
- **Specification**: codev/specs/30-feat-integrate-capability-map-.md
- **Created**: 2026-04-12

## Executive Summary

Implements the incremental enrichment approach from the spec. Work is broken into 5 phases building incrementally: schema extensions first, then auto-linking, then pipeline integration, then UI, and finally additional seller context fields. Each phase is independently testable and committable.

## Success Metrics
- [ ] All specification success criteria met
- [ ] Test coverage for all new code
- [ ] Existing tests continue to pass
- [ ] Backward compatibility verified (existing configs/maps load without error)
- [ ] Enriched drafts use explicit capability → sales_play → proof_point chain

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "schema_extensions", "title": "Phase 1: Schema Extensions"},
    {"id": "auto_linking", "title": "Phase 2: Auto-Linking Intelligence to Capabilities"},
    {"id": "pipeline_integration", "title": "Phase 3: Pipeline Integration"},
    {"id": "frontend_ui", "title": "Phase 4: Frontend UI"},
    {"id": "seller_context", "title": "Phase 5: Additional Seller Context Fields"}
  ]
}
```

## Phase Breakdown

### Phase 1: Schema Extensions
**Dependencies**: None

#### Objectives
- Extend `CapabilityMapEntry` with optional seller intelligence fields
- Add `industry` field to `CompanyState`
- Add `matched_capability_ids` to `SolutionMappingOutput`
- Ensure backward compatibility — existing configs/maps load without error

#### Deliverables
- [ ] Updated `CapabilityMapEntry` in `backend/config/capability_map.py` with `differentiators`, `sales_plays`, `proof_points` fields
- [ ] Updated `as_dict()` and YAML serialization to include new fields
- [ ] Updated `CompanyState` in `backend/models/state.py` with `industry: Optional[str]`
- [ ] Updated `SolutionMappingOutput` with `matched_capability_ids: List[str]`
- [ ] Unit tests: load capability map with/without new fields, verify defaults

#### Implementation Details

**`CapabilityMapEntry` changes** (`backend/config/capability_map.py`):
- Add to `__slots__`: `"differentiators"`, `"sales_plays"`, `"proof_points"`
- In `__init__`: 
  ```python
  self.differentiators: list[str] = data.get("differentiators") or []
  self.sales_plays: list[dict] = data.get("sales_plays") or []
  self.proof_points: list[dict] = data.get("proof_points") or []
  ```
- Update `as_dict()` to include the three new fields
- Sales plays use `{"play": str, "category": str}` dict format (matches `SalesPlayDict`)
- Proof points use `{"customer": str, "summary": str}` dict format (matches `ProofPointDict`)

**`CompanyState` changes** (`backend/models/state.py`):
- Add `industry: Optional[str]` after `research_result` field

**`SolutionMappingOutput` changes** (`backend/models/state.py`):
- Add `matched_capability_ids: List[str]` (defaults to `[]` in LLM parsing)

#### Evaluation Criteria
- Existing `capability_map.yaml` files load without error
- New fields default to empty lists when absent
- All existing tests pass unchanged
- `as_dict()` round-trips correctly with new fields

---

### Phase 2: Auto-Linking Intelligence to Capabilities
**Dependencies**: Phase 1

#### Objectives
- Implement LLM-based auto-linking that matches scraped seller intelligence to capability entries
- Integrate auto-linking into the seller intelligence extraction flow
- Add API endpoint for manual trigger

#### Deliverables
- [ ] `auto_link_intelligence()` function in `backend/agents/seller_intelligence.py` (keeps LLM dependency in the agent layer, not the pure data-loading `capability_map.py`)
- [ ] Integration with `extract_seller_intelligence()` — auto-link runs after successful scrape
- [ ] `POST /api/settings/capability-map/auto-link` endpoint
- [ ] Unit tests for auto-linking with mocked LLM responses

#### Implementation Details

**`auto_link_intelligence()` in `backend/agents/seller_intelligence.py`**:
- Takes `CapabilityMap` + `SellerIntelligence` + LLM config as input
- Makes a single LLM call with:
  - List of capability entries (id, label, solution_areas)
  - Full scraped intelligence (differentiators, sales_plays, proof_points)
  - Instruction: return JSON mapping `capability_id → {differentiators: [...], sales_plays: [...], proof_points: [...]}`
- **Truncation**: If total prompt exceeds ~8K tokens, truncate intelligence lists to top 10 items per category. Capability entries are always included in full (typically 3-6 entries).
- Parses LLM response and populates each `CapabilityMapEntry`'s new fields
- Saves updated capability map via `save_capability_map()` (imported from `capability_map.py`)
- Returns the mapping for UI display

**Integration with scraping**:
- At end of `extract_seller_intelligence()` in `seller_intelligence.py`, after saving to config:
  - Load capability map
  - If capability map exists and has entries, call `auto_link_intelligence()`
  - Log result (how many items linked to how many entries)

**API endpoint** in `backend/api/routes/settings.py`:
- `POST /api/settings/capability-map/auto-link` — triggers auto-linking using current seller intelligence and capability map
- Returns `{linked: {entry_id: {differentiators: [...], sales_plays: [...], proof_points: [...]}}, unlinked: {differentiators: [...], ...}}`

#### Evaluation Criteria
- Auto-linking correctly maps relevant items to capability entries
- Unmatched items are not lost (remain in global SellerIntelligence)
- Empty capability map → auto-link skipped gracefully
- Empty intelligence → auto-link returns empty mapping

---

### Phase 3: Pipeline Integration
**Dependencies**: Phase 1

#### Objectives
- Research agent classifies target company industry
- Solution mapping returns `matched_capability_ids`
- Persona generation uses industry for industry-specific titles
- Synthesis uses matched capability enrichment data + industry context
- Draft uses explicit capability → sales_play → proof_point chain
- All agents handle missing/stale data gracefully

#### Deliverables
- [ ] Updated research agent: industry classification from fixed taxonomy
- [ ] Updated solution mapping: return `matched_capability_ids` alongside solution_areas
- [ ] Updated persona generation: use industry for industry-specific persona titles
- [ ] Updated synthesis: incorporate matched capability's differentiators + proof_points + industry
- [ ] Updated draft: use explicit enrichment chain
- [ ] Updated pipeline: pass `capability_map` to synthesis and draft nodes; ensure availability on HITL resume path
- [ ] Integration tests: verify data flows through full pipeline
- [ ] Stale ID handling tests

#### Implementation Details

**Research agent** (`backend/agents/research.py`):
- Add `_run_industry_classification()` sub-task alongside existing company_context/tech_stack/hiring sub-tasks
- LLM prompt: given company name + signal summary, classify into one of: `fintech`, `healthcare`, `e-commerce`, `saas`, `cybersecurity`, `devtools`, `media`, `logistics`, `education`, `enterprise_software`, `other`
- Output a single string from the taxonomy
- On failure: return `None` (graceful degradation)
- Update `ResearchResult` TypedDict: no change needed — `industry` goes on `CompanyState` directly
- In `run_research()`, set `cs["industry"] = industry_result` after gathering sub-tasks

**Solution mapping** (`backend/agents/solution_mapping.py`):
- **Critical**: Update `_capability_map_to_text()` to include entry `id` in the output (currently only shows `label`). Without the `id`, the LLM cannot return valid `matched_capability_ids`. New format: `- [id: data-platform] Data Platform | signals: ... | areas: ...`
- Update `_build_solution_mapping_prompt()` to instruct LLM to also return `matched_capability_ids` — the IDs of capability entries whose solution_areas best match
- Update `_parse_solution_mapping_response()` to extract `matched_capability_ids` (default `[]` if field is absent from LLM response — graceful handling required)
- In `run_solution_mapping()`, populate `SolutionMappingOutput["matched_capability_ids"]`

**Persona generation** (`backend/agents/persona_generation.py`):
- Update `_build_persona_customization_prompt()` (or equivalent persona title generation) to accept `industry: Optional[str]`
- When `industry` is available, adjust persona titles to be industry-specific (e.g., "VP of Engineering" → "VP of Engineering, FinTech" or "Head of Clinical Data" for healthcare)
- When `industry` is `None`, generate generic titles (current behavior)
- Pass `industry` from `CompanyState` in `run_persona_generation()`

**Synthesis** (`backend/agents/synthesis.py`):
- Update `_build_synthesis_prompt()` to accept optional enrichment context (differentiators, proof_points from matched capabilities) AND `industry`
- Include industry in the prompt context: "Target company industry: {industry}" when available
- In `run_synthesis()`, look up matched capability entries and extract their enrichment data
- Pass enrichment data to the prompt as "Seller's specific angle on this problem"
- If no enrichment data or industry available, synthesis works as before (no degradation)

**Draft** (`backend/agents/draft.py`):
- Update `_build_seller_intelligence_section()` to accept matched capability enrichment data
- When matched capabilities have linked sales_plays/proof_points, use those specifically instead of the global list
- Fall back to global seller intelligence if no capability-specific data exists
- Add industry-aware messaging: if `CompanyState.industry` matches a `target_vertical`, note it in the prompt

**`company_pipeline` node** (`backend/pipeline.py`):
- Ensure `capability_map` object is passed through to synthesis and draft nodes (currently only passed to signal ingestion/qualification/solution_mapping)
- **HITL resume path**: When the pipeline resumes after persona selection, it re-enters `company_pipeline` with `skip_to_synthesis=True`. Verify that `capability_map` is available in the `CompanyInput` payload on resume (it's set at dispatch time via `input.get("capability_map")`). If the capability map was modified between pause and resume, the resume uses the version from dispatch — this is acceptable since the pipeline should use a consistent snapshot.

#### Evaluation Criteria
- Industry classification populates `CompanyState.industry` correctly
- `matched_capability_ids` flows from solution_mapping through synthesis to draft
- Persona titles reflect industry when available
- Synthesis prompt includes industry context and capability enrichment data
- Stale capability IDs (deleted entries) are skipped with warning log
- Drafts with enrichment data reference specific differentiators/proof_points
- Pipeline works unchanged when no enrichment data exists
- HITL resume path correctly passes `capability_map` to synthesis/draft

---

### Phase 4: Frontend UI
**Dependencies**: Phase 1, Phase 2

#### Objectives
- Allow users to view and edit seller intelligence per capability entry
- Show auto-link results and allow manual adjustment
- Add API endpoint for per-entry intelligence editing

#### Deliverables
- [ ] `PATCH /api/settings/capability-map/{entry_id}/intelligence` endpoint
- [ ] Updated CapabilityMapTab in frontend to show/edit per-entry intelligence
- [ ] Auto-link trigger button in UI
- [ ] TypeScript type updates in `frontend/src/types.ts`

#### Implementation Details

**API endpoint** in `backend/api/routes/settings.py`:
- `PATCH /api/settings/capability-map/{entry_id}/intelligence`
- Payload: `{differentiators?: string[], sales_plays?: SalesPlayDict[], proof_points?: ProofPointDict[]}`
- Loads capability map, finds entry by ID, updates its intelligence fields, saves

**Frontend** (`frontend/src/components/SettingsPanel.tsx`):
- In the CapabilityMapTab, each capability entry card gains an expandable "Seller Intelligence" section
- Shows linked differentiators, sales_plays, proof_points with inline edit/add/remove
- "Auto-Link" button calls POST `/api/settings/capability-map/auto-link` and refreshes the view
- Sales plays show `play` and `category` fields; proof points show `customer` and `summary`

**TypeScript types** (`frontend/src/types.ts`):
- Extend `CapabilityMapEntry` type with optional `differentiators`, `sales_plays`, `proof_points`

#### Evaluation Criteria
- Users can view per-entry intelligence in the Settings UI
- Users can edit/add/remove intelligence items per entry
- Auto-link button works and refreshes the display
- Changes persist to `capability_map.yaml` via API

---

### Phase 5: Additional Seller Context Fields
**Dependencies**: Phase 1

#### Objectives
- Add target_verticals, value_metrics, competitive_counters, company_size_messaging to seller profile
- Add UI for editing these fields
- Integrate into draft generation

#### Deliverables
- [ ] Updated `SellerProfileConfig` in `backend/config/loader.py` with new fields
- [ ] Updated `SellerProfile` TypedDict in `backend/models/state.py`
- [ ] `PUT /api/settings/seller-context` endpoint
- [ ] Frontend: new "Seller Context" section in SettingsPanel
- [ ] Draft agent uses target_verticals and value_metrics when available
- [ ] Tests for config loading, API endpoints, draft enrichment

#### Implementation Details

**Config models** (`backend/config/loader.py`):
```python
class SellerProfileConfig(BaseModel):
    # ... existing fields ...
    target_verticals: list[str] = Field(default_factory=list)
    value_metrics: list[str] = Field(default_factory=list)
    competitive_counters: dict[str, list[str]] = Field(default_factory=dict)
    company_size_messaging: dict[str, str] = Field(default_factory=dict)
```

**TypedDict** (`backend/models/state.py`):
```python
class SellerProfile(TypedDict):
    # ... existing fields ...
    target_verticals: NotRequired[List[str]]
    value_metrics: NotRequired[List[str]]
    competitive_counters: NotRequired[Dict[str, List[str]]]
    company_size_messaging: NotRequired[Dict[str, str]]
```

**API endpoint** (`backend/api/routes/settings.py`):
- `PUT /api/settings/seller-context` with payload matching the new fields
- Separate from seller-profile endpoint to avoid breaking existing clients

**Draft integration** (`backend/agents/draft.py`):
- If `target_verticals` includes the prospect's `industry` → note vertical alignment in prompt
- Include up to 3 `value_metrics` in the seller intelligence section
- `competitive_counters` and `company_size_messaging` available for future use but not injected into prompts in this phase (would require knowing the prospect's current vendor and company size — data not reliably available yet)

**Frontend** (`frontend/src/components/SettingsPanel.tsx`):
- New "Seller Context" tab or expandable section
- `target_verticals`: multi-select from industry taxonomy + custom input
- `value_metrics`: list editor (add/remove strings)
- `competitive_counters`: nested editor — competitor name → list of talking points
- `company_size_messaging`: three text areas (enterprise, mid_market, startup)

#### Evaluation Criteria
- New config fields load with empty defaults when absent
- API endpoint saves and retrieves all four fields
- Draft agent incorporates target_verticals and value_metrics
- UI allows editing all four fields

## Consultation Log

### Iteration 1 — Plan Review

**Gemini** (VERDICT: REQUEST_CHANGES, CONFIDENCE: HIGH):
- Added `persona_generation.py` updates to Phase 3 — spec requires industry-specific persona titles
- Fixed `_capability_map_to_text()` to include entry `id` — without it, LLM can't return valid `matched_capability_ids`
- Added `industry` to synthesis prompt context

**Claude** (VERDICT: COMMENT, CONFIDENCE: HIGH):
- Confirmed persona_generation gap (same as Gemini)
- Moved `auto_link_intelligence()` from `capability_map.py` to `seller_intelligence.py` — keeps LLM dependencies in agent layer
- Added truncation/chunking strategy for auto-linking LLM call
- Added HITL resume path verification — ensure `capability_map` available when pipeline resumes after persona selection
- Added explicit handling note for missing `matched_capability_ids` in LLM response parsing

**Codex**: Unavailable — usage limit reached.

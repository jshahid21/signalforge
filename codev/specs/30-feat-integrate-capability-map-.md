# Specification: Integrate Capability Map with Seller Intelligence + Manual Sales Plays

<!--
SPEC vs PLAN BOUNDARY:
This spec defines WHAT and WHY. The plan defines HOW and WHEN.
-->

## Metadata
- **ID**: spec-2026-04-12-integrate-capability-map
- **Status**: draft
- **Created**: 2026-04-12
- **Issue**: #30

## Clarifying Questions Asked

No clarifying questions needed — the issue provides a comprehensive problem statement with five distinct solution areas, and codebase analysis makes integration points unambiguous. Key decisions derived from analysis:

1. **Where does capability map live?** — `backend/config/capability_map.py` with `CapabilityMapEntry` (id, label, problem_signals, solution_areas) persisted in `~/.signalforge/capability_map.yaml`.
2. **Where does seller intelligence live?** — `backend/config/loader.py` (Pydantic: `SellerIntelligence`) and `backend/models/state.py` (TypedDict: `SellerIntelligenceDict`), stored in `~/.signalforge/config.json` as part of `SellerProfileConfig`.
3. **How are they currently connected?** — They are NOT connected. Capability map drives signal detection and solution mapping. Seller intelligence drives draft enrichment. They operate in parallel silos with no cross-linking.
4. **Where does industry appear?** — Only as free-text in `ResearchResult.company_context`. No structured field exists.
5. **UI for editing?** — `frontend/src/components/SettingsPanel.tsx` has a `CapabilityMapTab` for uploading/editing capability entries. Seller intelligence is displayed in a read-only section after scraping.

## Problem Statement

Capability map and seller intelligence are completely siloed in SignalForge:

- **Capability map** (`CapabilityMapEntry`) drives signal detection (`signal_ingestion.py` uses `all_keywords()` for density scoring) and solution mapping (`solution_mapping.py` uses entries as a "semantic scaffold").
- **Seller intelligence** (`SellerIntelligenceDict`) drives draft enrichment only (`draft.py:_build_seller_intelligence_section()` injects differentiators, sales plays, proof points into the draft prompt).

They never connect. When a signal matches a capability entry, the pipeline doesn't know the seller's specific angle on that problem until draft time — and even then the LLM must infer the connection between vendor-agnostic solution areas and seller-specific value props.

Additionally:
- **Sales plays from web scraping are generic** — they capture publicly stated use cases, not strategic internal knowledge like "when you see X signal in Y industry, lead with Z."
- **Industry is unstructured** — `ResearchResult.company_context` is free-text; there's no structured `industry` field for industry-aware messaging.
- **No seller context fields** for target verticals, value metrics, competitive counter-positioning, or company-size segmentation.

## Current State

### Capability Map
- **Schema**: `CapabilityMapEntry` with `id`, `label`, `problem_signals[]`, `solution_areas[]`
- **Storage**: `~/.signalforge/capability_map.yaml` (hot-reload, no caching)
- **Used by**: `signal_ingestion.py` (keyword density), `signal_qualification.py` (deterministic scoring), `solution_mapping.py` (semantic scaffold for LLM)
- **NOT used by**: `draft.py`, `synthesis.py`, `persona_generation.py`

### Seller Intelligence
- **Schema**: `SellerIntelligenceDict` with `differentiators[]`, `sales_plays[]`, `proof_points[]`, `competitive_positioning[]`, `last_scraped`
- **Storage**: Nested in `SellerProfileConfig` → `config.json`
- **Extracted by**: `seller_intelligence.py` (website scraping + LLM extraction)
- **Used by**: `draft.py:_build_seller_intelligence_section()` only
- **NOT used by**: `solution_mapping.py`, `synthesis.py`, `persona_generation.py`

### Pipeline Flow (current)
```
signal_ingestion (uses capability_map.all_keywords())
    → signal_qualification (uses capability_map keywords for deterministic_score)
    → research (produces free-text company_context)
    → solution_mapping (uses capability_map as semantic scaffold)
    → persona_generation (uses solution_areas + signal category)
    → synthesis (uses solution_areas + research)
    → draft (uses seller_intelligence separately — no link to which capability matched)
```

The gap: solution_mapping selects capability entries, but the downstream agents don't know which capability entry matched, so they can't pull the seller's specific differentiators/proof points/sales plays for that capability.

## Desired State

### 1. Enriched Capability Map Entries

Each `CapabilityMapEntry` gains seller intelligence fields that link it to the seller's specific value proposition:

```yaml
- id: platform-engineering
  label: Platform Engineering
  problem_signals: ["kubernetes", "platform team", "infrastructure scaling"]
  solution_areas: ["Container Orchestration", "Infrastructure Automation"]
  # NEW fields:
  differentiators: ["Multi-cloud orchestration with 99.99% uptime"]
  sales_plays:
    - play: "Platform scaling for high-growth engineering teams"
      category: "infrastructure"
  proof_points:
    - customer: "Stripe"
      summary: "Reduced deploy time by 60%"
```

- `differentiators`: `list[str]` — Subset of seller differentiators most relevant to this capability
- `sales_plays`: `list[SalesPlayDict]` — Strategic sales plays for this capability. Uses the same `{play, category}` structure as the existing `SellerIntelligence.sales_plays` field for consistency. Auto-linked from scraped data, then user-editable.
- `proof_points`: `list[ProofPointDict]` — Subset of proof points relevant to this capability. Uses the same `{customer, summary}` structure as existing `SellerIntelligence.proof_points`.

These fields are **optional** — existing capability maps without them continue to work. The structured types mirror the existing `SalesPlayDict` and `ProofPointDict` TypedDicts in `state.py` to avoid type divergence.

### 2. Manual Sales Play Input

Users can define/edit sales plays per capability entry through the UI:
- Web-scraped use cases pre-populate as suggestions
- Users verify and customize — sales plays are strategic internal knowledge
- Each capability entry's `sales_plays`, `differentiators`, and `proof_points` fields are editable inline
- Users can add new entries, edit existing ones, or remove irrelevant auto-linked items

### 3. Structured Industry Detection

Add a structured `industry` field to `CompanyState`:
- Research agent classifies the target company into a standard industry taxonomy
- Taxonomy: `fintech`, `healthcare`, `e-commerce`, `saas`, `cybersecurity`, `devtools`, `media`, `logistics`, `education`, `enterprise_software`, `other`
- Stored as `industry: Optional[str]` on `CompanyState`
- Used by persona generation (industry-specific titles) and synthesis/draft (industry-aware messaging)

### 4. Additional Seller Context Fields

Extend `SellerProfileConfig` and `SellerProfile` TypedDict with:
- **target_verticals**: `list[str]` — Industries the seller focuses on (e.g., `["fintech", "healthcare"]`)
- **value_metrics**: `list[str]` — Quantified outcomes (e.g., `"customers see 40% reduction in deploy time"`)
- **competitive_counters**: `dict[str, list[str]]` — Per-competitor talking points (e.g., `{"Datadog": ["50% lower cost", "no per-host pricing"]}`)
- **company_size_messaging**: `dict[str, str]` — Messaging variants by company size segment (e.g., `{"enterprise": "...", "mid_market": "...", "startup": "..."}`)

These fields are **optional** with sensible defaults (empty lists/dicts). They are user-configured via the Settings UI, not auto-scraped.

**UI complexity note**: `competitive_counters` (dict of competitor → list of talking points) requires a dynamic key-value editor. The Settings UI should use a simple add/remove pattern: user types a competitor name, then adds talking points as a list. This is a non-trivial UI component but follows established patterns (similar to how portfolio_items are edited today, just nested one level deeper).

### 5. Pipeline Integration

The enriched capability map flows through the entire pipeline:

```
signal_ingestion (unchanged — uses problem_signals)
    → signal_qualification (unchanged — uses deterministic_score)
    → research (NEW: classifies industry)
    → solution_mapping (NEW: returns matched_capability_ids alongside solution_areas)
    → persona_generation (NEW: uses industry for persona titles)
    → synthesis (NEW: uses matched capability's differentiators + proof points)
    → draft (NEW: gets explicit capability → sales_play → proof_point chain)
```

**Key change**: `SolutionMappingOutput` gains a `matched_capability_ids: list[str]` field. Downstream agents use these IDs to look up the enriched capability entries and access the seller's specific angle for each matched capability.

## Stakeholders
- **Primary Users**: Sales professionals configuring their capability map and sales plays
- **Secondary Users**: Sales managers reviewing draft quality
- **Technical Team**: AI builder (implementation), architect (review)

## Success Criteria

### Functional Requirements

1. **Enriched capability map schema**: `CapabilityMapEntry` supports optional `differentiators: list[str]`, `sales_plays: list[SalesPlayDict]`, `proof_points: list[ProofPointDict]` fields. Existing maps without these fields load without error (default to `[]`).
2. **Auto-linking**: After seller intelligence scraping completes, a linking function in `backend/config/capability_map.py` uses a single LLM call to match scraped intelligence items to capability entries by semantic relevance. The LLM receives the full list of capability entries (id + label + solution_areas) and the scraped intelligence, and returns a mapping of capability_id → {differentiators, sales_plays, proof_points}. Unmatched items remain in the global `SellerIntelligence` but are not linked to any capability entry. The user can review and edit the auto-linked results via the UI.
3. **Manual sales play editing**: UI allows users to view, edit, and add sales plays per capability entry. Scraped values pre-populate as suggestions.
4. **Structured industry**: `CompanyState` includes `industry: Optional[str]`. Research agent populates it from a fixed taxonomy. If classification fails, `industry` remains `None` and downstream agents degrade gracefully (skip industry-specific logic, use generic messaging).
5. **Seller context fields**: `target_verticals`, `value_metrics`, `competitive_counters`, `company_size_messaging` are configurable via Settings UI and persist to config.
6. **Matched capability IDs**: `SolutionMappingOutput` includes `matched_capability_ids: list[str]`. If a matched ID references a capability entry that was later deleted, downstream agents skip that ID gracefully (log a warning, continue without the enrichment data).
7. **Draft enrichment chain**: Draft agent receives explicit `capability → sales_plays → proof_points` chain instead of inferring connections.
8. **Backward compatibility**: All new fields are optional. Existing configs, capability maps, and pipeline state work without modification.
9. **API endpoints**: 
   - `PATCH /api/settings/capability-map/{entry_id}/intelligence` — Update seller intelligence fields (differentiators, sales_plays, proof_points) for a specific capability entry. Payload: `{differentiators?: string[], sales_plays?: SalesPlayDict[], proof_points?: ProofPointDict[]}`. Merges with existing entry and persists to `capability_map.yaml`.
   - `POST /api/settings/capability-map/auto-link` — Trigger auto-linking of current seller intelligence to capability entries. Returns the proposed mapping for user review.
   - `PUT /api/settings/seller-context` — Save additional seller context fields (target_verticals, value_metrics, competitive_counters, company_size_messaging). Payload mirrors the new config fields.

### Non-Functional Requirements

1. **No new external API calls** — enrichment uses existing scraped data + LLM calls already in the pipeline
2. **Hot-reload preserved** — capability map changes (including new fields) take effect on next pipeline run
3. **Config migration** — existing `config.json` and `capability_map.yaml` files are forward-compatible (missing new fields default to empty)

## Solution Approach

### Approach: Incremental Enrichment (Recommended)

Extend existing data structures rather than creating new ones. The capability map schema gains optional seller intelligence fields. A new linking step after seller intelligence scraping matches scraped data to capability entries. Pipeline agents are updated to pass matched capability IDs downstream.

**Why this approach**:
- Minimal schema churn — extends existing `CapabilityMapEntry`, `SellerProfileConfig`, `CompanyState`, `SolutionMappingOutput`
- Backward compatible — all new fields are optional with empty defaults
- Leverages existing infrastructure — hot-reload capability map, config persistence, Settings UI tabs
- Incremental delivery — each sub-feature (enriched schema, auto-linking, manual editing, industry, pipeline integration) can be implemented and tested independently

**Trade-offs**:
- Capability map YAML file grows larger with seller intelligence fields per entry
- Auto-linking quality depends on LLM semantic matching (may need user verification)
- Industry taxonomy is fixed — may need extension over time

### Alternative Considered: Separate Linking Table

Create a separate `capability_seller_links.yaml` mapping capability IDs to seller intelligence items. Rejected because it adds a new config file, a new loader, and synchronization complexity between two files — the inline approach is simpler and keeps related data together.

## Scope

### In Scope
1. Extend `CapabilityMapEntry` schema with seller intelligence fields
2. Auto-link seller intelligence to capability entries after scraping
3. UI for manual sales play editing per capability entry
4. Structured `industry` field on `CompanyState` + research agent classification
5. Additional seller context fields on `SellerProfileConfig`
6. `matched_capability_ids` on `SolutionMappingOutput`
7. Pipeline integration: solution_mapping → synthesis → draft use enriched capabilities
8. Backend API endpoints for editing capability entry seller intelligence
9. Tests for all new functionality

### Out of Scope
- Re-scraping seller website (already implemented in #20)
- Capability map auto-generation (already exists in `capability_map_generator.py`)
- Real-time industry classification (uses existing research agent LLM call)
- Competitive intelligence scraping (competitive_counters are user-entered, not auto-scraped)
- Advanced ML-based auto-linking (simple LLM-based semantic matching is sufficient)

## Edge Cases and Error Handling

1. **Deleted capability entry with linked intelligence**: If a user deletes a capability entry that has seller intelligence linked to it, the linked items (differentiators, sales_plays, proof_points) are lost from that entry. They remain in the global `SellerIntelligence` store and can be re-linked via auto-link or manual editing on other entries.
2. **Stale `matched_capability_ids`**: If `SolutionMappingOutput.matched_capability_ids` references a capability ID that was deleted between pipeline runs, downstream agents (synthesis, draft) skip the stale ID with a warning log. They still use any remaining valid IDs and fall back to the global seller intelligence if no valid matches remain.
3. **Auto-linking produces zero matches**: If no scraped intelligence items match any capability entry, all items remain in the global `SellerIntelligence` only. The UI shows the unlinked items and allows manual assignment.
4. **Industry classification failure**: If the research agent's LLM call fails to classify industry, `industry` remains `None`. Persona generation uses generic titles (current behavior). Synthesis and draft skip industry-specific messaging sections.
5. **Empty capability map**: If no capability map is configured, auto-linking is skipped. Pipeline operates as today with global seller intelligence only.
6. **Concurrent edits**: Capability map is hot-reloaded on each pipeline run. If a user edits intelligence fields while a pipeline is running, the running pipeline uses the version loaded at start. Next run picks up changes.

## Testing Strategy

1. **Unit tests**: Schema changes — verify `CapabilityMapEntry` loads with and without new optional fields; verify `CompanyState` with/without `industry`; verify new config fields default correctly.
2. **Auto-linking tests**: Mock LLM response to verify linking function correctly maps intelligence items to capability entries; test with empty capability map, empty intelligence, partial matches.
3. **Pipeline integration tests**: Verify `matched_capability_ids` flows from solution_mapping through synthesis to draft; verify stale ID handling; verify industry field propagation.
4. **API endpoint tests**: PATCH capability intelligence, POST auto-link, PUT seller context — success and validation error cases.
5. **Backward compatibility tests**: Load existing `capability_map.yaml` and `config.json` without new fields; verify no errors.

## Open Questions

None critical. All integration points are well-defined in the existing codebase.

- **Nice-to-know**: Should the industry taxonomy be user-extensible? Starting with a fixed list is simpler; can be extended later if needed.
- **Nice-to-know**: Should auto-linking run automatically after every scrape, or be user-triggered? Recommend automatic with user ability to review/edit results.

## Consultation Log

### Iteration 1 — Spec Review

**Claude** (VERDICT: REQUEST_CHANGES, CONFIDENCE: HIGH):
- Fixed `SettingsModal.tsx` → `SettingsPanel.tsx` filename error
- Reconciled `sales_play: str` (singular) → `sales_plays: list[SalesPlayDict]` (plural, structured) to match existing `SellerIntelligence` schema
- Added auto-linking step detail: where it runs (`capability_map.py`), what LLM call it uses (single call with full context), how ambiguous/zero matches are handled
- Added edge cases: deleted capability entries, stale `matched_capability_ids`, failed industry classification, empty capability map
- Added API endpoint specifications (PATCH intelligence, POST auto-link, PUT seller context)
- Acknowledged `competitive_counters` UI complexity with implementation guidance
- Added testing strategy with specific test categories

**Gemini**: Consultation completed but produced no review output (tool limitation).

**Codex**: Unavailable — usage limit reached.

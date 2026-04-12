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
5. **UI for editing?** — `frontend/src/components/SettingsModal.tsx` has a `CapabilityMapTab` for uploading/editing capability entries. Seller intelligence is displayed in a read-only section after scraping.

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
  sales_play: "Platform scaling for high-growth engineering teams"
  proof_points: ["Stripe: reduced deploy time by 60%"]
```

- `differentiators`: Subset of seller differentiators most relevant to this capability
- `sales_play`: A single strategic sales play for this capability (user-authored or scraped-then-edited)
- `proof_points`: Subset of proof points most relevant to this capability

These fields are **optional** — existing capability maps without them continue to work.

### 2. Manual Sales Play Input

Users can define/edit sales plays per capability entry through the UI:
- Web-scraped use cases pre-populate as suggestions
- Users verify and customize — sales plays are strategic internal knowledge
- Each capability entry's `sales_play` field is editable inline
- The `differentiators` and `proof_points` per entry are also editable

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

1. **Enriched capability map schema**: `CapabilityMapEntry` supports optional `differentiators`, `sales_play`, `proof_points` fields. Existing maps without these fields load without error.
2. **Auto-linking**: After seller intelligence scraping, a linking step matches scraped differentiators/proof points/sales plays to capability entries based on semantic relevance.
3. **Manual sales play editing**: UI allows users to view, edit, and add sales plays per capability entry. Scraped values pre-populate as suggestions.
4. **Structured industry**: `CompanyState` includes `industry: Optional[str]`. Research agent populates it from a fixed taxonomy. Pipeline agents use it when available.
5. **Seller context fields**: `target_verticals`, `value_metrics`, `competitive_counters`, `company_size_messaging` are configurable via Settings UI and persist to config.
6. **Matched capability IDs**: `SolutionMappingOutput` includes `matched_capability_ids` so downstream agents can look up enriched capability data.
7. **Draft enrichment chain**: Draft agent receives explicit `capability → sales_play → proof_point` chain instead of inferring connections.
8. **Backward compatibility**: All new fields are optional. Existing configs, capability maps, and pipeline state work without modification.

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

## Open Questions

None critical. All integration points are well-defined in the existing codebase.

- **Nice-to-know**: Should the industry taxonomy be user-extensible? Starting with a fixed list is simpler; can be extended later if needed.
- **Nice-to-know**: Should auto-linking run automatically after every scrape, or be user-triggered? Recommend automatic with user ability to review/edit results.

## Consultation Log

*To be populated after 3-way consultation.*

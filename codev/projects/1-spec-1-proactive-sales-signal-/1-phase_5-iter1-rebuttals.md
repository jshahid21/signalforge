# Phase 5 Iter 1 — Rebuttal

## Issues Addressed

### 1. HITL interrupt/resume not wired into LangGraph (Codex + Gemini)

**Problem**: `hitl_persona_selection_node` was defined in `hitl_gate.py` but never added to the graph. `company_pipeline` returned early with `awaiting_persona_selection=True` instead of using LangGraph's native `interrupt()` mechanism.

**Fix**:
- Rewrote `hitl_gate.py` → new `hitl_gate_node(state: AgentState)` that:
  1. Detects companies with `current_stage == "awaiting_persona_selection"` in `company_states`
  2. Calls `langgraph.types.interrupt()` to pause the graph (LangGraph's native mechanism)
  3. On resume, receives `{company_id: [persona_id, ...]}` from `Command(resume=...)`
  4. Applies selections via `apply_persona_selection()` and dispatches synthesis-only `company_pipeline` runs via `Command(send=[Send(...)])`
- Updated `build_pipeline()` in `pipeline.py`:
  - Compiles graph with `MemorySaver()` checkpointer (required for interrupt/resume)
  - Wires: `company_pipeline → hitl_gate → END` (was: `company_pipeline → END`)
  - Adds `hitl_gate` node to graph

The synthesis-only `company_pipeline` runs use the existing `skip_to_synthesis` guard (already in place) to jump directly to the synthesis+draft stages.

### 2. Missing HITL pause/resume test (Codex)

**Fix**: Added `tests/test_hitl.py` with 9 tests covering:
- `TestRunPersonaSelectionGate`: marks state as `AWAITING_HUMAN`, sets stage, no mutation of original
- `TestApplyPersonaSelection`: applies valid selections, skips unknown IDs, handles empty selection
- `TestHITLPauseResumeCycle`: full pause→resume cycle at functional level; verifies `skip_to_synthesis` conditions are satisfied after selection

### 3. Missing HumanReviewReason tracking (Gemini)

**Three reasons were not implemented. All three are now tracked:**

**`SIGNAL_AMBIGUOUS`** — added to `signal_qualification.py`:
- After computing `ambiguity_score`, if `ambiguity_score > 0.7` and `tier_used != SignalTier.TIER_2` (no Tier 2 resolution), sets `human_review_required=True` and appends `HumanReviewReason.SIGNAL_AMBIGUOUS`

**`PERSONA_UNRESOLVED`** — added to `persona_generation.py`:
- After generating personas, if `len(personas) < 2`, sets `human_review_required=True` and appends `HumanReviewReason.PERSONA_UNRESOLVED`

**`DRAFT_QUALITY`** — added to `draft.py`:
- `run_draft` now retries LLM call up to 2 attempts (was 1)
- If both attempts fail to produce parseable JSON, sets `human_review_required=True` and appends `HumanReviewReason.DRAFT_QUALITY` to the company state

## Test Results

```
233 passed, 1 warning in 0.91s
```

All existing tests continue to pass. 9 new HITL tests added.

## Architectural Note on HITL + Send()

LangGraph's `interrupt()` within `Send()` fan-out nodes restarts the node from the top on resume. The synthesis-only dispatch from `hitl_gate_node` passes updated `company_state` (with `selected_personas` and `current_stage="synthesis"`) in a fresh `CompanyInput`, so the restarted `company_pipeline` correctly skips ingestion/research and proceeds to synthesis. This is the recommended pattern for HITL with parallel fan-out in LangGraph.

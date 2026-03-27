# Plan Review Rebuttal — Iteration 1

## Summary

All REQUEST_CHANGES and substantive COMMENT issues have been addressed with plan updates. No issues were rejected.

---

## Codex — REQUEST_CHANGES

### 1. Budget enforcement placement (misplaced in API layer)
**Change made**: Added explicit in-agent budget enforcement language to Phase 3. Each agent checks `AgentState.total_cost_usd >= session_budget.max_usd` before any API call or Tier escalation. If the cap is reached, the operation is skipped and the company is marked FAILED with reason `budget_exceeded`. This is enforced in the graph nodes themselves, not the API layer, precisely because LangGraph runs nodes asynchronously and cannot be interrupted from outside.

### 2. Capability map generation missing URL crawling/extraction step
**Change made**: Phase 4 now explicitly lists all three input modes from spec §8.1: (1) product list (paste SKUs), (2) product URL with crawl/extract, (3) territory text. Added `backend/tools/web_crawler.py` as a deliverable for URL crawling. Phase 4 implementation details now detail the full 3-mode generation process.

### 3. HumanReviewReason mapping not planned
**Change made**: Phase 5 implementation details now explicitly map which agent sets which `HumanReviewReason` enum value and under what condition:
- `LOW_CONFIDENCE` → Solution Mapping Agent (confidence < 50)
- `SIGNAL_AMBIGUOUS` → Signal Qualification Agent (ambiguity_score > 0.7 unresolved)
- `PERSONA_UNRESOLVED` → Persona Generation Agent (< 2 personas generated)
- `DRAFT_QUALITY` → Draft Agent (regeneration fails after 2 attempts)

### 4. Session persistence — frontend rehydration not addressed
**Change made**: Phase 7 now explicitly calls out session rehydration behavior: on app load, fetch latest session from API (backed by `SqliteSaver` checkpointer), restore HITL gate state if `awaiting_persona_selection = true`, restore drafts. Zustand store is populated from API response on mount.

---

## Gemini — COMMENT

### LangGraph State Reducers
**Change made**: Phase 2 now explicitly documents which `AgentState` fields require `Annotated` reducers due to parallel `Send()` branch updates: `total_cost_usd` (operator.add), `completed_company_ids` / `failed_company_ids` / `final_drafts` (operator.concat), and `company_states` (custom `merge_dict` reducer). Phase 2 acceptance criteria now includes reducer correctness tests.

### LangGraph native checkpointer for session persistence
**Change made**: Phase 6 now specifies `SqliteSaver` from `langgraph.checkpoint.sqlite` as the checkpointer (replacing the earlier vague "serialize AgentState to SQLite"). Session resume is now correctly described as `graph.invoke(None, config={"configurable": {"thread_id": session_id}})`. This is intrinsically required for the `interrupt()` API to work correctly.

### Budget halting via in-agent checks (not API layer)
**Change made**: Same as Codex issue #1 above — addressed in Phase 3 with explicit in-agent budget enforcement.

---

## Claude — COMMENT

### Missing Capability Map tab in Settings UI
**Change made**: Phase 7 `SettingsPanel.tsx` now lists 5 tabs including the Capability Map tab (read-only table view, add/delete entries, Regenerate button) per spec §8.1/§9.9.

### `recommended_outreach_sequence` not addressed
**Change made**: Phase 4 now documents the `recommended_outreach_sequence` logic: start with `influencer` or `technical_buyer` for technical signals, then `economic_buyer`. Avoid leading with exec unless strategic signal. This is computed by the Persona Generation Agent and stored in `CompanyState`.

### Phase 8 was overloaded (Chat Agent + fixtures + E2E + eval)
**Change made**: Chat Assistant agent implementation moved to Phase 5 (alongside other agents). Phase 8 is now scoped to integration tests, E2E tests, fixtures, and the LLM eval harness only.

### LangGraph `Send()` aggregation/reduce step not detailed
**Change made**: Phase 2 now explains the aggregation model: per-company states are merged into `AgentState.company_states` via the `merge_dict` reducer. Each company writes only to its own `company_id` key. This is documented in both Phase 2 (reducers) and Phase 3 (orchestrator).

### LangGraph checkpointer for session resume
**Change made**: Same as Gemini issue above — `SqliteSaver` specified in Phase 6.

### Capability map generation inputs underspecified
**Change made**: Same as Codex issue #2 — all three input modes now documented in Phase 4.

---

## Items not changed

- **Frontend test coverage (beyond manual)**: The plan does not add React Testing Library tests. The spec does not require frontend test coverage, and adding a full frontend test suite is out of scope for this plan. The risk is acknowledged but the tradeoff is accepted for a local-first single-user app.
- **LangGraph version pinning**: Version pinning is an implementation-time decision (will be in `pyproject.toml`). The plan note "LangGraph 0.2+" is intentionally a minimum floor, not a pin — pinning happens at scaffold time in Phase 1.
- **SSE vs WebSocket for chat**: SSE is used for chat streaming because it's simpler (unidirectional, works over standard HTTP, no upgrade handshake) and appropriate for a request/response streaming pattern. WebSocket is used for pipeline progress because it's bidirectional and long-lived. This is a deliberate design choice, not an oversight.

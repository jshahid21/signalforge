# Review: Proactive Sales Signal Intelligence Engine (Spec 1)

## Summary

Implemented a full-stack AI sales signal pipeline: FastAPI backend + React frontend + LangGraph
StateGraph orchestrator. The system monitors up to 5 target companies, qualifies buying signals
from job postings (JSearch Tier 1, Tavily Tier 2), maps them to seller capabilities, generates
personas, synthesizes insights, and drafts personalized outreach emails. HITL persona selection
is wired via LangGraph interrupt/resume. The frontend provides a workspace UI with company
pipeline status, persona selection, insights panel, draft review, and settings management.

**8 implementation phases, 316 passing tests, LLM eval harness (draft_eval.py) for offline scoring.**

---

## Spec Compliance

- [x] §2 Signal Ingestion: JSearch Tier 1 + Tavily Tier 2 + signal_ambiguity_score escalation
- [x] §3 Signal Qualification: deterministic scoring + LLM severity + composite threshold
- [x] §4 Solution Mapping: capability map matching + LLM-assisted mapping + confidence gate
- [x] §5 Persona Generation: deterministic rule-based (no LLM), HITL pause/resume, custom personas
- [x] §5.7 HITL Gate: LangGraph interrupt()/Command(resume=...) via hitl_gate_node
- [x] §6 Draft Generation: per-persona synthesis + draft with few-shot memory injection
- [x] §7 Memory Agent: SQLite-backed approved draft retrieval for few-shot examples
- [x] §8 API Layer: FastAPI REST + WebSocket session streaming + SSE for chat
- [x] §9 React Frontend: full workspace with company table, persona table, insights, drafts, settings
- [x] §9.8 Override Flow: DraftPanel with override reason → `POST /sessions/{id}/override`
- [x] §9.9 Settings: API Keys, Seller Profile, Capability Map CRUD tabs
- [x] §10 Configuration: `config.yaml` + `capability_map.yaml` loader with validation
- [x] §13.2 Integration Tests: 6 scenarios + parametrized fixture tests
- [x] §13.3 E2E Tests: full pipeline, HITL, memory injection, budget enforcement
- [x] §13.4 LLM Eval Harness: 3-dimension judge rubric (technical_credibility, tone_adherence, no_generic_phrases)

### Deviations

- **`recommended_outreach_sequence`** (§4): Field defined in the state model but display in the
  frontend InsightsPanel was omitted. The backend populates it, but the UI does not render it.
  Gemini flagged this in the plan phase. It was deprioritized as a non-blocking spec comment.
- **Tier 3 escalation** fully stubbed: Spec §2 mentions Tier 3 as a future extension. No
  company can trigger Tier 3 in this implementation (no third data source). Codex flagged this
  in phase 3 but it was rebutted as explicitly deferred by spec.
- **Parallel StateGraph concurrency test**: `test_parallel_companies_no_state_collision` tests
  the reducer function, not actual LangGraph concurrent node execution. Gemini flagged this as
  optional in phase 8.

---

## Lessons Learned

### What Went Well

- **LangGraph HITL wiring via interrupt()/Command(resume=...)**: Once the pattern was established
  (hitl_gate_node calls `langgraph_interrupt()`, resumes via `Command(resume={company_id: [...]})`,
  re-dispatches synthesis via `Command(goto=[Send(...)])`), the implementation was clean and the
  API integration followed naturally.
- **Agent-level mocking strategy**: Patching at the agent function level (`call_llm_severity`,
  `_run_company_context`, etc.) rather than module imports made integration tests resilient to
  internal refactors.
- **TypedDict for all state models**: Avoided Pydantic model overhead in LangGraph state, kept
  reducer logic simple with `merge_dict` helpers.
- **3-way consultation catching real bugs early**: Phase 5 consultation caught `break → continue`
  in the draft retry loop before integration tests could. Phase 3 consultation caught the
  `signal_ambiguity_score` never being wired into Tier 2 escalation.

### Challenges Encountered

- **`Command(goto=...)` vs `Command(send=...)`**: LangGraph 1.1.3 uses `goto`, not `send`. The
  old API silently accepted `send` as a keyword argument, causing hitl_gate resumption to never
  dispatch synthesis runs. Caught by examining `Command.__init__` signature.
- **`from X import Y` patch targeting**: When `pipeline.py` does `from backend.agents.draft import
  run_drafts_for_company`, patching `backend.agents.draft.run_drafts_for_company` has no effect —
  only `backend.pipeline.run_drafts_for_company` works. This caused the memory injection test to
  fail silently in pytest while appearing to work in direct Python runs.
- **AsyncSqliteSaver resource lifecycle**: `__aenter__()` / `__aexit__()` must be paired. Using
  the context manager directly instead of manual `__aenter__` calls resolved the resource leak.
- **LangGraph interrupt + MemorySaver in tests**: `interrupt()` requires a checkpointer. Tests
  using `build_pipeline(checkpointer=MemorySaver())` passed; tests without a checkpointer raised
  obscure errors. Solution: always pass `MemorySaver()` in E2E tests.

### What Would Be Done Differently

- **Specify the `session` concept more precisely upfront**: "Session" appeared in §8 (API) with
  implicit budget scoping but was never formally defined in the spec. This caused ambiguity in
  state persistence design (in-memory vs. checkpointer-backed). Claude raised this in spec review.
- **Break Phase 8 earlier**: Combining E2E tests + integration tests + LLM eval harness into one
  phase was too much. Gemini flagged this in plan review. Should have been 2 phases.
- **Add `signal_ambiguity_score` to the spec's escalation criteria table**: The field was defined
  in the state schema but the escalation logic never referenced it. Three reviewers (Gemini phase 3,
  Codex phase 3, Claude phase 3) caught this. A clear spec table would have prevented the omission.

### Methodology Improvements

- **Patch target cheatsheet in CLAUDE.md**: Document the "patch at point of use, not definition"
  rule for Python mocking. e.g., `from X import Y` → patch `module_where_it_is_used.Y`.
- **E2E test quality gate**: Add a rule: E2E tests for qualified fixtures must not allow FAILED/SKIPPED.
  Reviewers flagged loose assertions in phase 8. A convention would prevent this regression.

---

## Technical Debt

- `recommended_outreach_sequence` is never displayed in the frontend InsightsPanel (§4).
- Tier 3 escalation is fully stubbed. If a third data source (e.g., news crawl) is added later,
  `run_signal_ingestion` must be extended.
- `parallel StateGraph concurrency` is not tested at the LangGraph level — only the reducer is
  tested. A multi-company concurrent graph execution test would give higher confidence.
- The capability map generator (`backend/agents/capability_map_generator.py`) has no unit tests.
  Web crawling logic in `backend/tools/web_crawler.py` also lacks tests.

---

## Consultation Feedback

### Specify Phase (Round 1)

#### Claude
- **Concern**: Seller Profile injection into Draft Agent not fully specified
  - **Addressed**: Phase 6 wired `seller_profile` from session state into `company_pipeline` → `run_drafts_for_company`
- **Concern**: "Session" concept undefined — cost budget scoping ambiguous
  - **Addressed**: Phase 6 defined session as the unit of budget tracking (`config.session_budget.max_usd`), scoped per API session invocation
- **Concern**: 50–59 confidence range for review flag vs. draft gate not documented
  - **Addressed**: Kept as-is with comment in draft agent; intentional gap between flag (50) and gate (60) to allow human review override

#### Codex
- **Concern**: Missing/ambiguous scoring definitions and thresholds
  - **Addressed**: Phase 2 formalized `QualifiedSignal` with all scoring fields; Phase 3 implemented composite score formula
- **Concern**: HITL override behavior not specified in state/governance
  - **Addressed**: Phase 5 added `HumanReviewReason` enum; Phase 7 added override flow with reason field
- **Concern**: Data retention/privacy controls insufficient
  - **Rebutted**: Scope deferred to production hardening; spec §13 does not include privacy as an acceptance criterion
- **Concern**: Cost budgeting vs stage count unclear
  - **Addressed**: Phase 6 clarified: budget is USD-denominated, checked at each agent before LLM calls
- **Concern**: Fallback source configuration undefined
  - **Rebutted**: Tier 3 explicitly deferred; fallback = empty result set when Tier 2 returns nothing

#### Gemini
- **Concern**: None — APPROVE

---

### Plan Phase (Round 1)

#### Claude
- **Concern**: LangGraph State Reducers must handle parallel branch updates
  - **Addressed**: Phase 2 implemented `merge_dict`, `append_list` reducers on all shared AgentState fields
- **Concern**: Use `AsyncSqliteSaver` checkpointer, not manual serialization
  - **Addressed**: Phase 6 uses `AsyncSqliteSaver` for persistent sessions; `MemorySaver` for tests
- **Concern**: Budget checks must be in agents, not just API layer
  - **Addressed**: Phase 3 added `current_total_cost >= max_budget_usd` guard in each agent

#### Codex
- **Concern**: Budget enforcement underspecified and misplaced
  - **Addressed**: Added per-agent budget checks returning FAILED status when exceeded
- **Concern**: Capability map generation omits product URL crawling step
  - **Addressed**: Phase 4 added `web_crawler.py` + `capability_map_generator.py` with URL crawl
- **Concern**: HITL review reasons mapping not planned
  - **Addressed**: Phase 5 added `HumanReviewReason` enum wiring
- **Concern**: Session persistence scope not fully clarified
  - **Addressed**: Phase 6 defined session lifecycle explicitly

#### Gemini
- **Concern**: Missing Capability Map tab in Settings UI
  - **Addressed**: Phase 7 added CapabilityMapTab with CRUD + backend `GET/POST/DELETE /settings/capability-map`
- **Concern**: `recommended_outreach_sequence` not addressed in any phase
  - **N/A**: Field is populated in solution mapping output but frontend display omitted as low-priority
- **Concern**: Phase 8 is overloaded (chat + fixtures + E2E + integration + eval)
  - **N/A**: Kept as single phase given timeline; acknowledged as technical debt
- **Concern**: LangGraph `Send()` aggregation step not detailed
  - **Addressed**: Phase 5 detailed `dispatch_companies` conditional edge + hitl_gate_node
- **Concern**: LangGraph checkpointer for session resume not specified
  - **Addressed**: Phase 6 uses `AsyncSqliteSaver` with thread_id = session_id

---

### Phase 1 (Round 1)

#### Claude
- **Concern**: Vite config missing `@tailwindcss/vite` plugin; App.tsx is boilerplate
  - **Addressed**: Phase 1 fix commit added Tailwind wiring; App.tsx replaced in Phase 7

#### Codex
- **Concern**: First-run setup wizard missing; Tailwind not wired; config loader missing required-key enforcement
  - **Addressed**: Tailwind wired; config loader enforces required keys with clear error messages; wizard deferred (not in spec)

#### Gemini
- **Concern**: `@tailwindcss/vite` missing from Vite config; `index.css` missing `@import "tailwindcss"`
  - **Addressed**: Fixed in Phase 1 review commit

---

### Phase 2 (Round 1)

#### Claude, Gemini
- **Concern**: None — APPROVE

#### Codex
- **Concern**: `SolutionMappingOutput.confidence_score` type mismatch; test coverage gaps
  - **Addressed**: Type aligned to `int` (0–100 range as per spec); coverage expanded

---

### Phase 3 (Round 1)

#### Claude
- **Concern**: `llm_tokens_used` overwrites rather than accumulates
  - **Addressed**: Fixed accumulation in signal_qualification.py
- **Concern**: `density == 0` branch unreachable dead code
  - **Addressed**: Removed dead branch
- **Concern**: `signal_ambiguity_score` never evaluated in Tier 2 escalation
  - **Addressed**: Phase 3 fix wired `compute_signal_ambiguity_score` output into escalation criteria

#### Codex
- **Concern**: Tier 3 fully stubbed; budget enforcement gaps; `signal_ambiguity_score` always None; `partial` flag missing
  - **Addressed**: Ambiguity score wired; `partial` field added to `QualifiedSignal`; Tier 3 deferred intentionally

#### Gemini
- **Concern**: `signal_ambiguity_score > 0.7` trigger bypassed; ambiguity score never computed before escalation decision
  - **Addressed**: `compute_signal_ambiguity_score` now called before Tier 2 escalation check

---

### Phase 4 (Round 1)

#### Claude
- **Concern**: `research.py` ignores budget parameters
  - **Addressed**: Added budget guard before LLM calls in research.py
- **Concern**: No tests for `capability_map_generator.py` or `web_crawler.py`
  - **N/A**: Kept as technical debt; core agents are tested; crawler is an IO wrapper

#### Codex
- **Concern**: Hiring persona bias includes economic buyer (violates spec)
  - **Addressed**: Persona generation rule updated to select purely on technical signal
- **Concern**: Inferred solution areas not tagged
  - **Addressed**: `SolutionMappingOutput.inferred_areas` field populated and tagged distinctly

#### Gemini
- **Concern**: `research.py` makes 3 parallel LLM calls without budget check
  - **Addressed**: Budget check added before each parallel research call
- **Concern**: `solution_mapping.py` uses fallback on budget exhaustion instead of FAILED
  - **Addressed**: Returns FAILED status when budget exceeded before mapping call

---

### Phase 5 (Round 1)

#### Claude
- **Concern**: `draft.py` `except Exception: break` should be `continue`
  - **Addressed**: Fixed in Phase 5 fix commit

#### Codex
- **Concern**: HITL interrupt/resume not actually wired into LangGraph; missing HITL tests
  - **Addressed**: Phase 5 fix fully wired `hitl_gate_node` into graph; HITL tests added in test_api.py

#### Gemini
- **Concern**: `hitl_gate_node` created but never registered in `pipeline.py` graph
  - **Addressed**: Phase 5 fix registered node + edges in `build_pipeline()`
- **Concern**: `HumanReviewReason.DRAFT_QUALITY` missing; SIGNAL_AMBIGUOUS/PERSONA_UNRESOLVED not implemented
  - **Addressed**: Full `HumanReviewReason` enum + wiring in draft.py and signal_qualification.py

---

### Phase 6 (Round 1)

#### Claude
- **Concern**: Missing `POST /sessions/{id}/resume` endpoint
  - **Addressed**: Phase 6 fix added the resume endpoint
- **Concern**: `AsyncSqliteSaver` resource leak (`__aenter__` without `__aexit__`)
  - **Addressed**: Fixed with proper async context manager usage
- **Concern**: WebSocket events batched, not real-time; missing HITL resume / chat SSE tests
  - **Addressed**: Events emitted per-stage; chat SSE tests added in test_api.py

#### Codex
- **Concern**: Missing `/sessions/{id}/resume`; WebSocket stage events not per-stage; status enum serialized incorrectly
  - **Addressed**: Resume endpoint added; per-stage WS events; status serialized as `.value`

#### Gemini
- **Concern**: Session rehydration bypasses `AsyncSqliteSaver` if session not in memory; state mutations not persisted; custom personas dropped during resume
  - **Addressed**: Phase 6 fix unified persistence through checkpointer; custom personas included in HITL resume payload

---

### Phase 7 (Round 1)

#### Claude
- **Concern**: `index.css #root` leftover Vite scaffold styles break workspace layout
  - **Addressed**: Phase 7 fix removed scaffold CSS from index.css
- **Concern**: `onOverride` prop never passed to DraftPanel in App.tsx
  - **Addressed**: Wired `onOverride` → `handleOverride` → `POST /sessions/{id}/override`

#### Codex
- **Concern**: HITL override flow missing; InsightsPanel not persona-scoped; PersonaTable missing remove/add; CapabilityMap tab incomplete; company status filtering absent; WebSocket handlers accumulate across session switches
  - **Addressed**: All fixed in Phase 7 review commit

#### Gemini
- **Concern**: CapabilityMap CRUD missing; override flow missing; persona removal missing; `technical_context` missing from InsightsPanel
  - **Addressed**: All fixed in Phase 7 review commit; `technical_context` added to `SynthesisOutput` and rendered in InsightsPanel

---

### Phase 8 (Round 1)

#### Claude
- **Concern**: E2E assertions accept FAILED/SKIPPED for qualified fixtures; memory injection test tests the mock; cost accumulation test trivially true; fixtures not used
  - **Addressed**: All fixed in Phase 8 fix commit

#### Codex
- **Concern**: Fixtures not used in tests; memory injection not exercised through pipeline; Tier 2 suppression not verified; SKIPPED scenario not validated; full pipeline run incomplete
  - **Addressed**: Added parametrized fixture tests, `test_tier1_sufficient_tavily_not_called`, `test_fixture_qualified_company_reaches_persona_stage`; memory injection test now calls `company_pipeline`

#### Gemini
- **Concern**: `COMPANY_FIXTURES` never used in tests
  - **Addressed**: Added parametrized tests over all 10 fixtures in `test_integration.py`
- **Concern**: Parallel concurrency test too shallow
  - **N/A**: Acknowledged as optional by Gemini; kept as technical debt

---

## Architecture Updates

Updated `codev/resources/arch.md` with the full SignalForge architecture:
- Pipeline topology (LangGraph StateGraph nodes, edges, HITL flow)
- Agent directory structure and responsibilities
- State model (AgentState, CompanyState, TypedDicts)
- API layer (FastAPI routes, WebSocket, SSE)
- Frontend component tree (React + Vite + Tailwind)
- Tool integrations (JSearch, Tavily, SQLite memory)
- Configuration files (`config.yaml`, `capability_map.yaml`)

---

## Lessons Learned Updates

Added the following entries to `codev/resources/lessons-learned.md`:
- **Testing**: "patch at point of use, not definition" — `from X import Y` means patch `module.Y`, not `X.Y`
- **Testing**: E2E tests for qualified fixtures must forbid SKIPPED/FAILED outcomes
- **Architecture**: LangGraph `Command(goto=...)` not `Command(send=...)` in version 1.1.3+
- **Architecture**: LangGraph interrupt() requires a checkpointer — always pass `MemorySaver()` in tests
- **Process**: Break overloaded phases early — Phase 8 combining 5 deliverables caused rushed tests

---

## Flaky Tests

No flaky tests encountered. All 316 tests pass consistently.

---

## Follow-up Items

- Add `recommended_outreach_sequence` display to InsightsPanel (`frontend/src/components/InsightsPanel.tsx`)
- Add unit tests for `backend/agents/capability_map_generator.py` and `backend/tools/web_crawler.py`
- Add full concurrent LangGraph execution test (5 companies in parallel via StateGraph)
- Implement Tier 3 escalation when a third data source becomes available

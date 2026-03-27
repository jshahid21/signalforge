# Implementation Plan: SignalForge — Proactive Sales Signal Intelligence Engine

## Metadata
- **ID**: plan-2026-03-27-signalforge
- **Status**: draft
- **Specification**: `codev/specs/1-proactive-sales-signal-intelligence-engine.md` (v1.4)
- **Created**: 2026-03-27

## Executive Summary

SignalForge is a LangGraph multi-agent pipeline + React workspace UI. The implementation is split into 8 phases organized by dependency order:

1. **Project scaffold** — repo structure, dependency setup, config management
2. **Data models & state schema** — Python TypedDicts with LangGraph reducers, Pydantic models, enums
3. **Signal ingestion & qualification agents** — tiered acquisition, scoring, in-agent budget enforcement
4. **Research, solution mapping, persona generation** — parallel sub-tasks, capability map generation (URL crawling + product list + territory), outreach sequence logic
5. **Synthesis, draft, memory & chat agents** — HITL gate, draft confidence gate, memory, chat assistant
6. **API layer** — FastAPI REST + WebSocket, `SqliteSaver` LangGraph checkpointer for session persistence
7. **React frontend workspace** — all panels including Capability Map Settings tab, session rehydration on resume
8. **Integration & end-to-end tests** — Full pipeline tests, HITL flow, fixture-based E2E, LLM eval

Each phase is independently testable and commits atomically.

## Success Metrics
- [ ] Pipeline processes 1–5 companies in parallel without state collision
- [ ] Cost-tiered signal acquisition (Tier 1 always, Tier 2/3 conditional)
- [ ] Signal qualification composite scoring (deterministic + LLM)
- [ ] HITL persona selection gate pauses pipeline correctly
- [ ] Draft generated with confidence ≥ 60; skipped below 60
- [ ] Memory store persists approved drafts and injects them as few-shot examples
- [ ] React UI with all 5 panels functional
- [ ] Session budget cap enforced ($0.50 default)
- [ ] All unit + integration tests pass

## Phases (Machine Readable)

<!-- REQUIRED: porch uses this JSON to track phase progress. Update this when adding/removing phases. -->

```json
{
  "phases": [
    {"id": "phase_1", "title": "Project Scaffold & Configuration"},
    {"id": "phase_2", "title": "Data Models & State Schema"},
    {"id": "phase_3", "title": "Signal Ingestion & Qualification Agents"},
    {"id": "phase_4", "title": "Research, Solution Mapping & Persona Generation Agents"},
    {"id": "phase_5", "title": "Synthesis, Draft & Memory Agents"},
    {"id": "phase_6", "title": "API Layer (FastAPI + WebSocket)"},
    {"id": "phase_7", "title": "React Frontend Workspace"},
    {"id": "phase_8", "title": "Chat Assistant & End-to-End Tests"}
  ]
}
```

## Phase Breakdown

---

### Phase 1: Project Scaffold & Configuration
**Dependencies**: None

#### Objectives
- Set up Python backend project structure with dependency management
- Set up React frontend project structure
- Implement local config management (API keys, seller profile, capability map)
- Implement first-run setup wizard logic (CLI/API)

#### Deliverables
- [ ] `backend/` — Python package with `pyproject.toml` or `requirements.txt`
- [ ] `backend/config/` — Config loader, schema, and `~/.signalforge/config.json` management
- [ ] `backend/config/seller_profile.py` — SellerProfile config read/write
- [ ] `backend/config/capability_map.py` — CapabilityMap loader and hot-reload support
- [ ] `frontend/` — Vite + React scaffolded app
- [ ] `tests/` — Test directory with `conftest.py`
- [ ] `tests/fixtures/` — 10 canonical company fixture stubs (populated in Phase 8)
- [ ] `.env.example` — Documents required env vars

#### Implementation Details
- Python backend: `langgraph`, `langchain`, `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `httpx`, `tavily-python`
- Frontend: React + Vite, `axios`, `zustand` (state), Tailwind CSS
- Config file at `~/.signalforge/config.json`:
  ```json
  {
    "seller_profile": { "company_name": "", "portfolio_summary": "", "portfolio_items": [] },
    "api_keys": { "jsearch": "", "tavily": "", "llm_provider": "", "llm_model": "" },
    "session_budget": { "max_usd": 0.50, "tier3_limit": 1 },
    "capability_map_path": "~/.signalforge/capability_map.yaml"
  }
  ```
- Capability map is hot-reloadable: loader re-reads file on each pipeline run (no restart)
- First-run detection: if `config.json` missing or `seller_profile.company_name` is empty → flag `first_run = True` (Setup Wizard triggered by API)

#### Acceptance Criteria
- [ ] `python -m backend` starts without error
- [ ] Config file created on first run with defaults
- [ ] `npm run dev` starts React app
- [ ] Config loader unit tests pass

#### Test Plan
- **Unit Tests**: Config loader parses valid JSON, raises on missing required keys
- **Unit Tests**: CapabilityMap loader handles valid YAML, missing fields, and malformed entries (per spec §13.1)

---

### Phase 2: Data Models & State Schema
**Dependencies**: Phase 1

#### Objectives
- Implement all TypedDicts/Pydantic models from spec §4 with LangGraph reducers for parallel-safe global state
- Implement enums (`SignalTier`, `PipelineStatus`, `HumanReviewReason`)
- Implement `MemoryRecord` schema and SQLite table definition

#### Deliverables
- [ ] `backend/models/state.py` — All TypedDicts with reducers: `RawSignal`, `QualifiedSignal`, `ResearchResult`, `SolutionMappingOutput`, `Persona`, `SynthesisOutput`, `Draft`, `CostMetadata`, `CompanyError`, `SellerProfile`, `CompanyState`, `AgentState`
- [ ] `backend/models/enums.py` — `SignalTier`, `PipelineStatus`, `HumanReviewReason`
- [ ] `backend/models/memory.py` — `MemoryRecord` dataclass + SQLAlchemy model
- [ ] `backend/db.py` — SQLite engine setup, table creation on startup
- [ ] `tests/test_models.py` — Model instantiation and validation tests

#### Implementation Details
- Use Python `TypedDict` for LangGraph state (required by LangGraph)
- **LangGraph reducers for parallel-safe global state**: Fields updated by parallel `Send()` branches must use `Annotated` reducers to prevent concurrent overwrite:
  - `total_cost_usd: Annotated[float, operator.add]` — accumulates cost across companies
  - `completed_company_ids: Annotated[List[str], operator.concat]`
  - `failed_company_ids: Annotated[List[str], operator.concat]`
  - `final_drafts: Annotated[List[Draft], operator.concat]`
  - `company_states: Annotated[Dict[str, CompanyState], merge_dict]` — custom reducer merges by company_id key
- **Aggregation after `Send()` fan-out**: The orchestrator collects per-company `CompanyState` results dispatched by LangGraph and merges them into `AgentState.company_states` using the `merge_dict` reducer. Each company writes only to its own `company_id` key, preventing cross-company collision.
- Use Pydantic `BaseModel` for API request/response serialization (separate from TypedDicts)
- `SolutionMappingOutput.confidence_score` is 0–100 integer scale (per spec §5.5 note)
- `Draft.version` starts at 1 and increments on regeneration
- SQLite at `~/.signalforge/memory.db`; schema auto-created on startup via SQLAlchemy

#### Acceptance Criteria
- [ ] All models instantiate without error
- [ ] `CompanyState` correctly initializes all optional fields as `None` / empty lists
- [ ] `AgentState` uses `Annotated` reducers on `total_cost_usd`, `completed_company_ids`, `failed_company_ids`, `final_drafts`, `company_states`
- [ ] SQLite table created on `db.init()`
- [ ] Model tests pass

#### Test Plan
- **Unit Tests**: Instantiate each model with valid and invalid data
- **Unit Tests**: Verify reducer behavior — two parallel updates to `total_cost_usd` accumulate (not overwrite)
- **Unit Tests**: Verify `merge_dict` reducer merges by key without collision

---

### Phase 3: Signal Ingestion & Qualification Agents
**Dependencies**: Phase 2

#### Objectives
- Implement `SignalIngestionAgent` with cost-tiered Tier 1/2/3 logic
- Implement `SignalQualificationAgent` with deterministic + LLM scoring
- Implement company name normalization (slug generation) in `OrchestratorAgent`
- Implement LangGraph `StateGraph` skeleton with `Send()` API for parallel dispatch

#### Deliverables
- [ ] `backend/agents/orchestrator.py` — Input validation, slug normalization, `Send()` fan-out
- [ ] `backend/agents/signal_ingestion.py` — Tiered signal acquisition (JSearch Tier 1, Tavily Tier 2, configurable Tier 3)
- [ ] `backend/agents/signal_qualification.py` — Deterministic score, LLM severity score (4 sub-dimensions), composite score, threshold gate
- [ ] `backend/pipeline.py` — LangGraph `StateGraph` wiring (no agent logic — just graph assembly)
- [ ] `backend/tools/jsearch.py` — JSearch API client wrapper
- [ ] `backend/tools/tavily.py` — Tavily client wrapper
- [ ] `tests/test_orchestrator.py` — Slug normalization, input validation
- [ ] `tests/test_signal_ingestion.py` — Tiered logic with mocked API clients
- [ ] `tests/test_signal_qualification.py` — Scoring boundary values (59, 60, 61 per spec §13.1)

#### Implementation Details
- **Slug normalization** (spec §5.1): lowercase → strip legal suffixes → replace non-alphanum with `-` → collapse `-` → trim
- **Tier 1 escalation** triggers (any one): signal density < 3, deterministic_score == 0, signal_ambiguity_score > 0.7
- **Tier 2 escalation** triggers (both): composite_score ≥ 0.75 AND enterprise budget indicators
- **LLM severity output**: structured JSON `{"recency": f, "specificity": f, "technical_depth": f, "buying_intent": f}`; fallback to deterministic-only on JSON parse failure
- **Composite score**: `0.4 * deterministic_score + 0.6 * llm_severity_score`; threshold `0.45`
- **Cost logging**: every tier transition logs tier, reason, estimated cost, signal count to `CostMetadata`
- **In-agent budget enforcement**: Each agent checks `AgentState.total_cost_usd >= session_budget.max_usd` before any API call or Tier escalation. If cap is reached: skip the operation, mark company as `FAILED` with reason `budget_exceeded`, emit a WebSocket budget-exceeded event. This is enforced in the agent nodes themselves (not the API layer), because LangGraph nodes run asynchronously and cannot be killed mid-execution from outside.
- Retry policy: signal source calls 2 retries with exponential backoff; LLM calls 1 retry on rate limit

#### Acceptance Criteria
- [ ] `"Stripe, Inc."` → slug `"stripe"`, `"Upbound Group"` → `"upbound"`
- [ ] Duplicate slug detection raises correct error message
- [ ] Tier 1 always executes; Tier 2 only when threshold triggered
- [ ] LLM JSON parse failure falls back to deterministic score with `partial: true`
- [ ] Qualification threshold gate: score < 0.45 → `signal_qualified = false`
- [ ] Unit tests pass

#### Test Plan
- **Unit Tests**: Slug normalization for all spec examples
- **Unit Tests**: Tier escalation boundary conditions
- **Unit Tests**: Scoring formula boundary values (59, 60, 61 maps to qualification/draft thresholds)
- **Integration Tests**: 1 company with all Tier 1 signals → no Tier 2 calls made

---

### Phase 4: Research, Solution Mapping & Persona Generation Agents
**Dependencies**: Phase 3

#### Objectives
- Implement `ResearchAgent` with parallel sub-tasks (company context, tech stack, hiring signals)
- Implement `SolutionMappingAgent` (LLM-first, capability map as scaffold, vendor-agnostic)
- Implement `PersonaGenerationAgent` with signal→persona bias mapping

#### Deliverables
- [ ] `backend/agents/research.py` — Parallel sub-tasks: company context, tech stack extraction (explicit only), hiring signal analysis
- [ ] `backend/agents/solution_mapping.py` — LLM-first reasoning over capability map, confidence scoring, vendor-agnostic output
- [ ] `backend/agents/persona_generation.py` — Balanced buying group generation with signal→persona bias rules
- [ ] `backend/capability_map_generator.py` — LLM-based capability map generation from seller profile inputs (product list, product URL with crawl/extract, territory text)
- [ ] `backend/tools/web_crawler.py` — Lightweight URL crawler for product page extraction (used by capability map generator)
- [ ] `tests/test_research.py` — Graceful degradation on sub-task failure
- [ ] `tests/test_solution_mapping.py` — Vendor name validation, confidence thresholds
- [ ] `tests/test_persona_generation.py` — Signal→persona bias rules

#### Implementation Details
- **Research Agent**: 3 sub-tasks via `asyncio.gather()` (graceful — each wraps in try/except, `partial: true` if any fail)
- **Tech stack**: must only include explicitly stated technologies — no inference
- **Solution Mapping**: confidence < 50 → `human_review_required = true`; confidence < 60 → draft skipped (enforced in Draft Agent)
- **Novel solution areas**: tagged `inferred: true` in output when LLM generates outside capability map
- **Persona bias rules** must be applied deterministically based on signal type (spec §5.6 table)
- **Capability Map Generation** (spec §8.1) — three input modes the LLM groups into problem-domain categories:
  1. **Product list**: paste SKU/service names; LLM groups into capability categories
  2. **Product URL**: crawl/extract product names + descriptions from URL (via `web_crawler.py`); LLM groups extracted content
  3. **Territory text**: free-text focus area description; LLM generates categories from context
  - For each category, LLM generates `problem_signals` (semantic anchors) + `solution_areas` (vendor-agnostic)
  - Output saved as `~/.signalforge/capability_map.yaml`
- Map is hot-reloadable; generation triggered by first-run wizard and Settings UI
- **`recommended_outreach_sequence`** (spec §4/§5.6): Persona Generation Agent computes this ordered list after generating personas. Sequencing logic: start with `influencer` or `technical_buyer` if signal is technical (hiring/infra/ML signals), then `economic_buyer`. Avoid leading with `exec` unless signal is strategic (funding, cost optimization). This field is populated in `CompanyState` and displayed in the persona table as a suggested order.

#### Acceptance Criteria
- [ ] Research agent continues if any sub-task fails (sets `partial: true`)
- [ ] Solution mapping never outputs vendor product names in `solution_areas`
- [ ] Confidence < 50 sets `human_review_required = true`
- [ ] Persona generation produces balanced buying group matching signal type
- [ ] Capability map YAML generated correctly from mock seller profile
- [ ] Tests pass

#### Test Plan
- **Unit Tests**: Research partial failure scenarios
- **Unit Tests**: Solution mapping confidence thresholds (49, 50, 59, 60)
- **Unit Tests**: Persona bias rules (ML signal → Head of AI + ML Platform Lead + Senior ML Engineer)
- **Integration Tests**: Full pipeline through persona generation with mock LLM

---

### Phase 5: Synthesis, Draft & Memory Agents
**Dependencies**: Phase 4

#### Objectives
- Implement `SynthesisAgent` (per `(company, persona)` pair, parallel)
- Implement `DraftAgent` with confidence gate, persona-aware tone, seller profile injection, few-shot memory injection
- Implement `MemoryAgent` — write on approval, retrieve for few-shot
- Implement HITL persona selection gate in LangGraph (pipeline interrupt + resume)

#### Deliverables
- [ ] `backend/agents/synthesis.py` — All 7 `SynthesisOutput` fields per spec §5.8
- [ ] `backend/agents/draft.py` — Confidence gate (< 60 skip), persona-aware tone adaptation, seller profile injection, memory few-shot injection, versioning
- [ ] `backend/agents/memory_agent.py` — Write `MemoryRecord` on approval, retrieve top-2 for few-shot
- [ ] `backend/agents/hitl_gate.py` — LangGraph interrupt node for persona selection
- [ ] `backend/agents/chat_assistant.py` — Stateful chat agent with `CompanyState` context injection, streaming SSE output
- [ ] `backend/pipeline.py` — Updated with HITL gate wiring (interrupt + resume)
- [ ] `tests/test_synthesis.py` — All output fields populated
- [ ] `tests/test_draft.py` — Confidence gate boundary (59 skip, 60 generate), version increment
- [ ] `tests/test_memory.py` — Write/read memory records, few-shot retrieval
- [ ] `tests/test_chat_assistant.py` — Context block assembly, read-only constraint, streaming

#### Implementation Details
- **Synthesis**: runs in parallel for all selected personas via `asyncio.gather()`
- **Draft confidence gate**: `solution_mapping.confidence_score < 60` → skip draft, set `human_review_required = True`, add `LOW_CONFIDENCE` reason
- **Persona-aware tone**: role_type → focus/depth rules from spec §5.9 table
- **Seller profile injection**: inject `seller_profile.portfolio_items` into draft prompt; if no profile → vendor-agnostic draft + UI warning flag
- **Few-shot injection**: query memory store for up to 2 most recent approved drafts; inject into system prompt
- **Override flow**: `override_requested = true` → generate draft anyway; tag `drafted_under_override = true`; still eligible for memory
- **LangGraph HITL**: use `interrupt()` at persona selection node; pipeline resumes when `selected_personas` populated via API
- **HumanReviewReason tracking**: Agents must explicitly set reasons using the enum (not free text):
  - `LOW_CONFIDENCE` — `solution_mapping.confidence_score < 50` (Solution Mapping Agent)
  - `SIGNAL_AMBIGUOUS` — `signal_ambiguity_score > 0.7` without Tier 2 resolution (Signal Qualification Agent)
  - `PERSONA_UNRESOLVED` — persona generation produces < 2 personas (Persona Generation Agent)
  - `DRAFT_QUALITY` — draft regeneration fails after 2 attempts (Draft Agent)
  - Multiple reasons can accumulate; stored in `CompanyState.human_review_reasons` list
- **Chat Assistant agent** (spec §5.11): scoped to single `CompanyState`, read-only, streaming via SSE; context block injected at each turn; cannot trigger pipeline re-runs
- **Version**: `Draft.version` starts at 1, increments each time Draft Agent regenerates

#### Acceptance Criteria
- [ ] Draft skipped when confidence_score = 59; generated when = 60
- [ ] `Draft.version` increments on each regeneration call
- [ ] Memory record written on approval; retrieved in subsequent draft generation
- [ ] HITL gate: pipeline pauses at persona selection, resumes after API call with selected personas
- [ ] Override path: draft generated with `drafted_under_override = true`
- [ ] Tests pass

#### Test Plan
- **Unit Tests**: Draft confidence gate at boundaries
- **Unit Tests**: Version increment on regeneration
- **Integration Tests**: Memory write → read → injection in draft prompt
- **Integration Tests**: HITL gate pause/resume with simulated user input (per spec §13.3)

---

### Phase 6: API Layer (FastAPI + WebSocket)
**Dependencies**: Phase 5

#### Objectives
- Implement REST API endpoints for all pipeline operations
- Implement WebSocket for real-time streaming progress updates
- Implement session persistence (SQLite)

#### Deliverables
- [ ] `backend/api/routes/sessions.py` — `POST /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/resume`
- [ ] `backend/api/routes/companies.py` — `GET /sessions/{id}/companies`, `POST /sessions/{id}/companies/{cid}/retry`
- [ ] `backend/api/routes/personas.py` — `POST /sessions/{id}/companies/{cid}/personas/confirm`, `PUT /sessions/{id}/companies/{cid}/personas/{pid}`
- [ ] `backend/api/routes/drafts.py` — `POST /sessions/{id}/companies/{cid}/drafts/{pid}/regenerate`, `POST /sessions/{id}/companies/{cid}/drafts/{pid}/approve`
- [ ] `backend/api/routes/settings.py` — `GET/PUT /settings/seller-profile`, `GET/PUT /settings/api-keys`, `GET/PUT /settings/session-budget`, `POST /settings/capability-map/generate`
- [ ] `backend/api/routes/memory.py` — `GET /memory`, `DELETE /memory/{id}`, `GET /memory/export`
- [ ] `backend/api/routes/chat.py` — `POST /sessions/{id}/companies/{cid}/chat`
- [ ] `backend/api/routes/chat.py` — Chat SSE endpoint (moved agent to Phase 5)
- [ ] `backend/api/websocket.py` — WebSocket endpoint for pipeline progress events
- [ ] `backend/api/session_store.py` — LangGraph `SqliteSaver` checkpointer setup (replaces manual AgentState serialization)
- [ ] `tests/test_api.py` — API endpoint smoke tests

#### Implementation Details
- **LangGraph `SqliteSaver` checkpointer** (from `langgraph.checkpoint.sqlite`): used for all session persistence and HITL interrupt/resume. This is the native LangGraph mechanism — it automatically serializes graph state and enables `interrupt()` + resume semantics. The checkpointer DB file is `~/.signalforge/sessions.db`.
- WebSocket events: `{ type: "stage_update", company_id, stage, status }` — emitted at each agent completion
- **Pipeline status transitions** emitted as WebSocket events at each stage (per spec §6.4): `PENDING → RUNNING → AWAITING_HUMAN → RUNNING → COMPLETED / FAILED / SKIPPED`
- HITL gate exposed via `POST /sessions/{id}/companies/{cid}/personas/confirm` with `{ selected_persona_ids, custom_personas }`
- Draft approval via `POST .../approve` → triggers Memory Agent write
- `GET /memory/export` returns CSV of all MemoryRecords
- Session resume: call `graph.invoke(None, config={"configurable": {"thread_id": session_id}})` to resume from `SqliteSaver` checkpoint — no manual serialization needed
- Budget warning event: emit WebSocket event when `total_cost_usd >= 0.8 * session_budget.max_usd` (agents also enforce hard stop at cap)

#### Acceptance Criteria
- [ ] `POST /sessions` starts a pipeline run and returns session_id
- [ ] WebSocket streams stage updates in real time
- [ ] HITL confirm endpoint resumes pipeline
- [ ] Draft approve endpoint triggers memory write
- [ ] Session persists and is resumable after restart
- [ ] API smoke tests pass

#### Test Plan
- **Unit Tests**: Session serialization round-trip (AgentState → JSON → AgentState)
- **Integration Tests**: Full HTTP request cycle for key endpoints
- **Integration Tests**: WebSocket receives stage_update events during pipeline run

---

### Phase 7: React Frontend Workspace
**Dependencies**: Phase 6

#### Objectives
- Implement all 5 UI panels per spec §9
- Implement first-run setup wizard
- Implement Settings panel with all tabs
- Wire frontend to backend API and WebSocket

#### Deliverables
- [ ] `frontend/src/components/CompanyTable.tsx` — Company rows with status badges, confidence scores, filterable
- [ ] `frontend/src/components/PersonaTable.tsx` — Inline editing, add/remove, HITL selection with checkboxes
- [ ] `frontend/src/components/InsightsPanel.tsx` — Signal summary, core pain point, solution areas as tags, confidence badge
- [ ] `frontend/src/components/DraftPanel.tsx` — Editable subject/body, version indicator, Copy/Regenerate/Approve buttons
- [ ] `frontend/src/components/ChatAssistant.tsx` — Collapsible panel, scoped to selected company
- [ ] `frontend/src/components/ProgressBar.tsx` — Per-company 5-stage pipeline progress indicator
- [ ] `frontend/src/components/HumanReviewBadge.tsx` — Yellow warning badge with review reason
- [ ] `frontend/src/components/SettingsPanel.tsx` — Tabs: Seller Profile, API Keys, Session Budget, Memory Store, **Capability Map** (read-only table + add/delete entries + Regenerate button)
- [ ] `frontend/src/components/SetupWizard.tsx` — First-run wizard for seller profile + API key entry (all three capability map input modes: product list, product URL, territory text)
- [ ] `frontend/src/store/sessionStore.ts` — Zustand store for session state, pipeline status, selected company/persona
- [ ] `frontend/src/api/client.ts` — Axios API client + WebSocket connection manager
- [ ] `frontend/src/App.tsx` — Layout wiring: company table (left) + insights/draft (right) + chat (bottom)

#### Implementation Details
- **Session rehydration on app resume** (spec §3.4): On app load, fetch the most recent active session from API. If session state includes `awaiting_persona_selection = true`, restore the HITL gate UI. If session has drafts, restore them. All pipeline state comes from the API (backed by `SqliteSaver` checkpointer) — frontend Zustand store is populated from API response on mount.
- **Status badges**: color-coded (`pending` gray, `running` blue spinner, `completed` green, `failed` red, `skipped` gray, `awaiting_human` yellow)
- **HITL gate UI**: when `awaiting_persona_selection = true` → persona table shows selection mode with checkboxes + Confirm button
- **Human review flag** (spec §9.8): yellow badge + "Draft not generated — confidence too low" + Override button
- **Override flow**: Override button → optional reason dialog → API call with `override_requested: true`
- **Progress bar** stages: Signals → Qualifying → Researching → Mapping → Generating (5 stages)
- **Inline draft editing**: edits are local state only (do not trigger API calls)
- **Copy button**: one-click, no confirmation (per spec §9.5)
- **Budget warning**: WebSocket event → toast notification at 80% of session budget
- **All-companies-skipped state** (spec §9.10): show "No actionable signals found" message with suggestions
- **Session history**: list of previous sessions in sidebar (read-only)

#### Acceptance Criteria
- [ ] All 5 panels render with mock data
- [ ] Company row selection updates insights + draft panels
- [ ] HITL persona selection gate: checkboxes appear, Confirm resumes pipeline
- [ ] Inline draft editing works without triggering API
- [ ] Copy button copies to clipboard
- [ ] WebSocket updates progress in real time
- [ ] Setup wizard appears on first run
- [ ] Settings panel saves seller profile and API keys

#### Test Plan
- **Unit Tests**: CompanyTable renders status badges correctly
- **Unit Tests**: PersonaTable inline editing and custom persona add
- **Manual Testing**: Full workspace flow with real backend

---

### Phase 8: Integration & End-to-End Tests
**Dependencies**: Phase 7

#### Objectives
- Write comprehensive test fixtures (10 canonical companies)
- Write E2E tests covering all spec §13.3 scenarios
- Write integration tests covering all spec §13.2 scenarios
- Write LLM eval harness (spec §13.4)

#### Deliverables
- [ ] `tests/fixtures/companies.py` — 10 canonical company fixtures with expected tier, qualification, solution areas
- [ ] `tests/test_e2e.py` — Full pipeline E2E tests (LangChain fixture), HITL gate, memory injection, cost budget cap
- [ ] `tests/test_integration.py` — 5-company parallel (no state collision), partial research failure, custom persona synthesis, all spec §13.2 scenarios
- [ ] `tests/eval/draft_eval.py` — LLM-as-judge rubric for draft technical credibility and tone (spec §13.4)

#### Implementation Details
- **E2E test scenarios** (spec §13.3): full run with LangChain fixture, HITL pause/resume, memory injection verification, cost budget halt
- **Integration test scenarios** (spec §13.2):
  - 5 companies in parallel → verify no state key collision in `company_states` (reducer test)
  - 1 company with Tier 1 sufficient → verify no Tier 2 calls made
  - Signal qualification fails → company SKIPPED, rest continue unaffected
  - Partial research failure → `ResearchResult.partial = true`, pipeline continues
  - Low confidence score → draft not generated, `human_review_required = true`
  - User adds custom persona → Synthesis + Draft run for custom persona
- **Fixture format**: `{ company_name, expected_tier, expected_qualified, expected_signal_type, expected_solution_areas }`
- **LLM eval**: LLM-as-judge prompt evaluates draft on rubric: specificity (signal referenced), no generic phrases, tone match for role_type; run against 10 fixture companies
- All E2E tests use mock LLM + mock API clients (no real API calls in test suite)

#### Acceptance Criteria
- [ ] All 10 fixture companies produce expected results in integration tests
- [ ] 5-company parallel test: no state collision detected (reducer-based merging verified)
- [ ] HITL gate E2E: pipeline pauses, user input provided, pipeline resumes and completes
- [ ] Cost budget E2E: pipeline halts when `total_cost_usd >= session_budget.max_usd` (in-agent check)
- [ ] All spec §13.2 integration scenarios pass
- [ ] All tests pass

#### Test Plan
- **Integration Tests**: All 6 spec §13.2 scenarios with mock LLM
- **E2E Tests**: All spec §13.3 scenarios
- **LLM Eval**: Run `tests/eval/draft_eval.py` against fixture outputs (requires real LLM; separate from pytest)

---

## Dependency Map

```
Phase 1 (Scaffold)
    └─▶ Phase 2 (Models)
            └─▶ Phase 3 (Signal Ingestion + Qualification)
                    └─▶ Phase 4 (Research + Solution Mapping + Persona)
                                └─▶ Phase 5 (Synthesis + Draft + Memory + HITL)
                                            └─▶ Phase 6 (API Layer)
                                                        └─▶ Phase 7 (Frontend)
                                                                    └─▶ Phase 8 (Chat + E2E Tests)
```

## Risk Analysis

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LangGraph HITL interrupt/resume complexity | M | H | Use LangGraph `interrupt()` API; test early in Phase 5 |
| LLM structured JSON output failures | H | M | JSON parse fallback in Phase 3; retry with stricter prompt |
| State collision in parallel Send() pipelines | M | H | Each company gets isolated CompanyState copy; test in Phase 8 |
| Runaway Tier 3 cost | M | H | Session budget cap enforced in API layer (Phase 6); Tier 3 rate limit per session |
| Frontend WebSocket complexity | L | M | Use standard `reconnecting-websocket` library |

### Schedule Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LLM provider API changes | L | M | Abstract LLM calls behind `backend/llm.py` interface |
| JSearch API instability | M | M | Mock in all tests; graceful degradation in production |

## Post-Implementation Tasks

- [ ] Performance validation: verify < 90 seconds for 5 companies end-to-end
- [ ] Session budget cap validation: confirm pipeline halts correctly at $0.50
- [ ] LLM eval run against 20 labeled companies (spec §13.4)
- [ ] Memory store export tested with CSV download

## Notes

- **Capability map generation** is part of Phase 4, not Phase 1, because it requires LLM integration
- **Hot-reload**: capability map loader re-reads YAML on each pipeline run — no caching
- **No time estimates** per protocol constraints
- **Tech stack**: Python 3.11+, LangGraph 0.2+, FastAPI, React 18+, Vite, Zustand, SQLite
- **LLM provider**: abstracted — configurable (Claude Sonnet default, GPT-4o supported)

---

## Amendment History

<!-- When adding a TICK amendment, add a new entry below this line in chronological order -->

# Architecture

High-level architecture documentation for SignalForge. Updated during Spec 1 implementation.

## Overview

SignalForge is a proactive B2B sales signal intelligence engine. It monitors up to 5 target
companies for buying signals (job postings, web presence), qualifies them against a seller's
capability map, generates stakeholder personas, synthesizes insights, and drafts personalized
outreach emails. A React frontend provides a workspace UI with HITL persona selection.

## Directory Structure

```
signalforge/
├── backend/
│   ├── agents/              # LangGraph node functions (one file per agent)
│   │   ├── orchestrator.py  # Validates companies, dispatches company_pipeline via Send()
│   │   ├── signal_ingestion.py  # JSearch Tier 1 + Tavily Tier 2 + ambiguity scoring
│   │   ├── signal_qualification.py  # Deterministic + LLM severity → composite score
│   │   ├── research.py      # Company context, tech stack, hiring signal LLM extraction
│   │   ├── solution_mapping.py  # Capability map matching + LLM solution areas
│   │   ├── persona_generation.py  # Deterministic rule-based persona generation
│   │   ├── hitl_gate.py     # LangGraph interrupt/resume node for persona selection
│   │   ├── synthesis.py     # Per-persona buyer insight synthesis
│   │   ├── draft.py         # Per-persona outreach draft generation with few-shot
│   │   ├── memory_agent.py  # SQLite-backed approved draft retrieval
│   │   └── capability_map_generator.py  # URL crawl → capability map entries
│   ├── api/
│   │   ├── app.py           # FastAPI application factory
│   │   └── routes/
│   │       ├── sessions.py  # Session lifecycle, HITL resume, draft actions
│   │       ├── settings.py  # API keys, seller profile, capability map CRUD
│   │       └── chat.py      # SSE streaming chat assistant endpoint
│   ├── config/
│   │   ├── loader.py        # config.yaml loader with required-key validation
│   │   └── capability_map.py  # capability_map.yaml loader
│   ├── models/
│   │   ├── state.py         # AgentState, CompanyState, all TypedDicts
│   │   └── enums.py         # PipelineStatus, SignalTier, HumanReviewReason, etc.
│   └── tools/
│       ├── jsearch.py       # JSearchClient (Tier 1 job posting search)
│       ├── tavily.py        # TavilySearchClient (Tier 2 web search)
│       └── web_crawler.py   # URL crawl for capability map generation
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Root component: session start, company/pipeline state
│   │   ├── components/
│   │   │   ├── CompanyTable.tsx   # Company list with status, signal tier columns
│   │   │   ├── PersonaTable.tsx   # HITL persona selection + custom add/remove
│   │   │   ├── InsightsPanel.tsx  # Per-persona synthesis + technical context
│   │   │   ├── DraftPanel.tsx     # Draft review, approve, regenerate, override
│   │   │   └── SettingsModal.tsx  # ApiKeysTab, SellerProfileTab, CapabilityMapTab
│   │   ├── api/             # Typed API client (fetch wrappers for all endpoints)
│   │   └── types.ts         # Frontend TypeScript type mirrors of backend models
│   ├── vite.config.ts       # Vite + @tailwindcss/vite plugin
│   └── index.css            # Tailwind import only (no Vite scaffold styles)
├── backend/pipeline.py      # LangGraph StateGraph assembly
├── tests/
│   ├── fixtures/companies.py  # 10 canonical company fixtures with expected outcomes
│   ├── test_api.py          # FastAPI route tests (pytest + httpx AsyncClient)
│   ├── test_integration.py  # Agent-level integration tests (mocked LLM)
│   ├── test_e2e.py          # Full pipeline E2E tests (MemorySaver checkpointer)
│   └── eval/draft_eval.py   # LLM-as-judge eval harness (standalone CLI)
└── config/
    ├── config.yaml          # LLM provider, API keys, session budget
    └── capability_map.yaml  # Seller capability → solution area mappings
```

## Pipeline Topology

```
orchestrator
    │  [conditional_edges → dispatch_companies → Send("company_pipeline", CompanyInput)]
    ▼
company_pipeline (per-company, parallel)
    │  ingestion → qualification → research → solution_mapping → persona_generation
    │  → HITL gate (LangGraph interrupt) → synthesis → drafts
    ▼
hitl_gate
    │  [detects AWAITING_HUMAN, calls interrupt(), on resume dispatches synthesis
    │   via Command(goto=[Send("company_pipeline", ...)])]
    ▼
END
```

### HITL Flow

1. `company_pipeline` runs through persona_generation
2. If `selected_personas` is empty → `run_persona_selection_gate()` → returns `AWAITING_HUMAN`
3. `hitl_gate_node` calls `langgraph_interrupt({...})` — graph pauses
4. API receives persona selections → `graph.ainvoke(Command(resume={company_id: [...]}), config=config)`
5. `hitl_gate_node` resumes → `apply_persona_selection()` → `Command(goto=[Send("company_pipeline", ...)])`
6. `company_pipeline` runs with `skip_to_synthesis=True` → synthesis → drafts → COMPLETED

## State Model

All state is TypedDict-based (not Pydantic models).

- **`AgentState`**: Global graph state — `company_states`, `seller_profile`, `total_cost_usd`, `awaiting_persona_selection`
- **`CompanyState`**: Per-company state — all agent outputs keyed by `company_id`
- **`CompanyInput`**: Immutable input to `company_pipeline` node (via `Send()`)
- **Reducers**: `merge_dict` (company_states), `append_list` (list fields), `add_float` (costs)

## Key Design Decisions

- **`from X import Y` → patch `module.Y`**: `from X import Y` creates a local binding. Always patch at the point of use, not the source module (e.g., `backend.pipeline.run_drafts_for_company`, not `backend.agents.draft.run_drafts_for_company`).
- **LangGraph `Command(goto=...)` not `Command(send=...)`**: LangGraph 1.1.x uses `goto` for Send dispatching in Command returns.
- **`MemorySaver` for tests, `AsyncSqliteSaver` for production**: `interrupt()` requires a checkpointer; always pass explicitly in E2E tests.
- **Budget checks in every agent**: Each agent checks `current_total_cost >= max_budget_usd` before expensive calls. Returns FAILED on exhaustion.

## External Dependencies

| Dependency | Purpose |
|---|---|
| LangGraph 1.1.x | StateGraph, interrupt/resume, Send dispatching |
| LangChain Anthropic | Claude LLM calls |
| FastAPI | REST API + WebSocket + SSE |
| JSearch API | Tier 1 job posting search |
| Tavily API | Tier 2 web signal search |
| SQLite (aiosqlite) | Memory agent storage + session checkpointing |
| Vite + React + Tailwind | Frontend build |

## Configuration

- `config/config.yaml`: `api_keys.{anthropic,jsearch,tavily,llm_provider,llm_model}`, `session_budget.max_usd`
- `config/capability_map.yaml`: `items[].{capability, solution_areas, keywords}`

---

*Updated by Spec 1: Proactive Sales Signal Intelligence Engine (2026-03-27)*

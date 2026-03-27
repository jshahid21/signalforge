# Spec 1: Proactive Sales Signal Intelligence Engine

**Status**: Draft (Consultation Feedback Incorporated)
**Date**: 2026-03-26
**Version**: 1.3

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Target Users & Personas](#2-target-users--personas)
3. [System Architecture](#3-system-architecture)
4. [Data Models & State Schema](#4-data-models--state-schema)
5. [Agent Definitions](#5-agent-definitions)
6. [Execution Flow](#6-execution-flow)
7. [Signal Ingestion & Tiering](#7-signal-ingestion--tiering)
8. [Solution Mapping](#8-solution-mapping)
9. [UI Design](#9-ui-design)
10. [Cost Strategy](#10-cost-strategy)
11. [Error Handling & Fault Tolerance](#11-error-handling--fault-tolerance)
12. [Memory & Feedback System](#12-memory--feedback-system)
13. [Testing Strategy](#13-testing-strategy)
14. [Risks & Limitations](#14-risks--limitations)
15. [Success Criteria](#15-success-criteria)

---

## 1. Product Overview

### 1.1 Goal

The Proactive Sales Signal Intelligence Engine is an AI-powered system that helps cloud sales engineers, presales architects, and technical account executives identify real, technically grounded buying signals and convert them into high-quality, technically credible outreach.

### 1.2 Problem Statement

Current outbound sales workflows for technical sellers suffer from three core failures:

- **Generic messaging**: Outreach is not grounded in specific technical context of the target company.
- **Manual research burden**: Account research is time-consuming, inconsistent, and non-scalable.
- **Static lead lists**: Signal quality degrades quickly; there is no mechanism for freshness or relevance scoring.

### 1.3 Solution Summary

This system replaces:

| Replaced With | Replacement |
|---|---|
| Generic outbound messaging | Signal-driven, persona-targeted outreach |
| Manual account research | Automated, parallel multi-source intelligence |
| Static lead lists | Dynamic, cost-tiered signal ingestion with confidence scoring |

### 1.4 System Name

**SignalForge** — a workspace for forging technically credible sales signals into outreach.

---

## 2. Target Users & Personas

### 2.1 Primary User Types

#### Type A: Cloud Solutions Engineer / Presales Architect

- **Works at**: AWS, GCP, OCI, Azure, or AI infrastructure companies
- **Sells**: Cloud infrastructure, data platforms, AI/ML platforms
- **Core need**: Deep technical context to credibly position solutions against a specific company's architecture decisions and pain points
- **Workflow**: Researches accounts before calls, crafts tailored technical pitches
- **Setup requirement**: On first use, must configure their **Seller Profile** — including their company name and product portfolio (e.g., "Oracle Cloud Infrastructure — OCI Compute, Autonomous DB, OCI Data Flow, AI Services"). This context is injected into Solution Mapping and Draft generation so outreach is grounded in the seller's actual capabilities, not generic abstractions.

#### Type B: Technical Account Executive
- **Works at**: Hyperscalers or AI companies (e.g., Anthropic, Databricks, Snowflake, LangChain)
- **Sells**: Platform subscriptions, enterprise contracts, developer tooling
- **Core need**: High-quality signals that resonate with technical buyers without sounding generic
- **Workflow**: Qualifies inbound interest, drives expansion, identifies whitespace

### 2.2 Grounding Examples (Target Company Categories)

The system is designed to generalize, but these companies serve as canonical grounding examples for signal calibration, testing, and prompt engineering:

- LangChain
- Anthropic
- Databricks
- Snowflake
- Cloudflare
- Stripe
- Upbound Group (Rent-A-Center) — enterprise retail / FinTech infrastructure
- Staples — enterprise retail / procurement automation

---

## 3. System Architecture

### 3.1 Architectural Style

The system is built as a **LangGraph multi-agent pipeline** with:

- **Parallel company processing** using the `Send()` API
- **Cost-tiered signal acquisition** with conditional branching
- **Human-in-the-loop** persona selection before draft generation
- **Dual interface**: structured workspace GUI + conversational assistant

### 3.2 High-Level Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        SignalForge System                        │
│                                                                 │
│  ┌─────────────┐     ┌──────────────────────────────────────┐  │
│  │  Input Layer│     │        LangGraph Pipeline             │  │
│  │             │────▶│                                      │  │
│  │ - Company   │     │  Orchestrator                        │  │
│  │   names     │     │      │                               │  │
│  │ - (1–5)     │     │      ▼ (Send() API — per company)    │  │
│  └─────────────┘     │  ┌───────────────────────────────┐  │  │
│                       │  │   Company Pipeline (parallel) │  │  │
│  ┌─────────────┐     │  │                               │  │  │
│  │  UI Layer   │     │  │  Signal Ingestion Agent       │  │  │
│  │             │     │  │       ↓                       │  │  │
│  │ - Company   │     │  │  Signal Qualification Agent   │  │  │
│  │   Table     │◀────│  │       ↓                       │  │  │
│  │ - Persona   │     │  │  Research Layer (parallel)    │  │  │
│  │   Table     │     │  │       ↓                       │  │  │
│  │ - Insights  │     │  │  Solution Mapping Agent       │  │  │
│  │   Panel     │     │  │       ↓                       │  │  │
│  │ - Draft     │     │  │  Persona Generation Agent     │  │  │
│  │   Panel     │     │  │       ↓ [HITL GATE]           │  │  │
│  │ - Chat      │     │  │  Synthesis Agent              │  │  │
│  │   Assistant │     │  │       ↓ [Confidence Gate]     │  │  │
│  └─────────────┘     │  │  Draft Agent                  │  │  │
│                       │  └───────────────────────────────┘  │  │
│  ┌─────────────┐     │                                      │  │
│  │  Memory     │     │  Memory Agent (post-approval)        │  │
│  │  Store      │◀────│                                      │  │
│  └─────────────┘     └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Technology Stack (Specification Level)

| Layer | Technology |
|---|---|
| Pipeline orchestration | LangGraph (StateGraph + Send API) |
| LLM provider | Configurable (e.g., Claude 3.5 Sonnet, GPT-4o) |
| Signal sources | JSearch API (Tier 1), Tavily Web Search (Tier 2), configurable enrichment (Tier 3) |
| Capability map | JSON/YAML file — vendor-agnostic, user-configurable |
| Memory store | Persistent key-value store (e.g., SQLite, Redis, or file-based) |
| Frontend | React-based workspace (web app) |
| API layer | REST + WebSocket (streaming progress updates) |

### 3.4 Session Lifecycle

A **session** is a single pipeline run bound to one set of input company names and a Seller Profile.

| Behavior | Spec |
|---|---|
| Session start | User clicks "New Session" or submits company names |
| Session persistence | Sessions are persisted locally (indexed DB or SQLite) — user can close and resume |
| Session resume | Re-opening app restores last session state including pipeline status, HITL gate state, and generated drafts |
| Concurrent sessions | v1 supports one active session at a time; previous sessions are read-only in history |
| Cost budget scope | Per-session; the `$0.50` cap applies to one session run (not per company) |
| Session expiry | No automatic expiry in v1; user must manually clear sessions |

### 3.5 Authentication & API Key Management

**Deployment model (v1)**: Local-first single-user application. No multi-user accounts or server-side auth.

**API Key configuration**:
- All API keys (JSearch, Tavily, LLM provider) are stored in a local config file (e.g., `~/.signalforge/config.json` or environment variables)
- Keys are never transmitted to SignalForge servers
- First-run wizard prompts for required keys and validates connectivity
- Settings UI (Section 9.9) allows editing keys at any time

**Seller Profile configuration**:
- Configured on first run via setup wizard (required before first session)
- Accessible and editable at any time via Settings → Seller Profile
- Stored in local config alongside API keys

---

## 4. Data Models & State Schema

### 4.1 LangGraph AgentState (TypedDict)

This is the canonical state object that flows through the LangGraph pipeline. All agents read from and write to this schema. It is designed to:

- Support parallel execution of per-company pipelines via `Send()`
- Prevent state collision between parallel jobs (each company has an isolated sub-state keyed by `company_id`)
- Track cost and tier metadata at every stage

```python
# === ENUMS ===

class SignalTier(str, Enum):
    TIER_1 = "tier_1"   # Low cost: job postings, lightweight public signals
    TIER_2 = "tier_2"   # Moderate: web search, blog/engineering signals
    TIER_3 = "tier_3"   # High cost: deep enrichment

class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN = "awaiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"        # e.g., signal did not qualify

class HumanReviewReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    SIGNAL_AMBIGUOUS = "signal_ambiguous"
    PERSONA_UNRESOLVED = "persona_unresolved"
    DRAFT_QUALITY = "draft_quality"

# === CORE DATA MODELS ===

class RawSignal(TypedDict):
    source: str                # e.g., "jsearch", "tavily", "blog"
    signal_type: str           # e.g., "job_posting", "engineering_blog", "funding_news"
    content: str               # Raw text / excerpt
    url: Optional[str]
    published_at: Optional[str]
    tier: SignalTier

class QualifiedSignal(TypedDict):
    company_id: str
    summary: str               # LLM-generated signal summary
    signal_type: str
    keywords_matched: List[str]
    deterministic_score: float # 0.0–1.0 keyword-weight score
    llm_severity_score: float  # 0.0–1.0 LLM-assessed severity
    composite_score: float     # Weighted combination of both
    tier_used: SignalTier
    raw_signals: List[RawSignal]
    qualified: bool
    disqualification_reason: Optional[str]

class ResearchResult(TypedDict):
    company_context: Optional[str]    # General company/market context
    tech_stack: Optional[List[str]]   # Explicit mentions only; no inference
    hiring_signals: Optional[str]     # Summary of hiring trends
    partial: bool                     # True if some research tasks failed gracefully

class SolutionMappingOutput(TypedDict):
    core_problem: str
    solution_areas: List[str]         # Vendor-agnostic capability categories
    confidence_score: float           # 0–100
    reasoning: str

class Persona(TypedDict):
    persona_id: str
    title: str                        # e.g., "Head of Platform Engineering"
    targeting_reason: str             # Why this persona is relevant given the signal
    role_type: Literal["economic_buyer", "technical_buyer", "influencer", "blocker"]
    seniority_level: Literal["exec", "director", "manager", "ic"]
    priority_score: float             # 0–1: likelihood this persona should be targeted first
    is_custom: bool                   # True if user-added
    is_edited: bool                   # True if user modified the title

# Signal → Persona Bias Mapping (used by Persona Generation Agent)
# Ensures generated personas feel inevitable, not arbitrary:
#
#   Hiring (engineering)  → technical_buyer + influencer(s)
#   Infra scaling         → technical_buyer + economic_buyer
#   Cost optimization     → economic_buyer + FinOps influencer
#   ML/AI signals         → Head of AI (economic_buyer) + ML Platform Lead (technical_buyer)
#   Security/compliance   → blocker + economic_buyer

class SynthesisOutput(TypedDict):
    core_pain_point: str
    technical_context: str
    solution_alignment: str
    persona_targeting: str            # Specific to the selected persona
    buyer_relevance: str              # Why THIS persona specifically would care (business + technical angle)
    value_hypothesis: str             # What outcome this persona is likely optimizing for
    risk_if_ignored: str              # What happens if they don't solve this (urgency signal)

class Draft(TypedDict):
    draft_id: str
    company_id: str
    persona_id: str
    subject_line: str
    body: str
    confidence_score: float           # Inherited from solution mapping
    approved: bool
    version: int                      # Increments on regeneration

class CostMetadata(TypedDict):
    tier_1_calls: int
    tier_2_calls: int
    tier_3_calls: int
    llm_tokens_used: int
    estimated_cost_usd: float
    tier_escalation_reasons: List[str]

class CompanyError(TypedDict):
    stage: str                        # Which agent/stage failed
    error_type: str
    message: str
    recoverable: bool

class SellerProfile(TypedDict):
    company_name: str                 # e.g., "Oracle Cloud Infrastructure"
    portfolio_summary: str            # Free-text description of the seller's product portfolio
    portfolio_items: List[str]        # e.g., ["OCI Compute", "Autonomous DB", "OCI Data Flow"]

# === PER-COMPANY STATE ===

class CompanyState(TypedDict):
    # Identity
    company_id: str                   # Stable slug, e.g., "langchain"
    company_name: str                 # Display name

    # Pipeline status
    status: PipelineStatus
    current_stage: str

    # Signal layer
    raw_signals: List[RawSignal]
    qualified_signal: Optional[QualifiedSignal]
    signal_qualified: bool

    # Research layer
    research_result: Optional[ResearchResult]

    # Solution mapping
    solution_mapping: Optional[SolutionMappingOutput]

    # Persona layer
    generated_personas: List[Persona]
    selected_personas: List[str]           # List of persona_ids (user-selected)
    recommended_outreach_sequence: List[str]  # Ordered persona_ids (system-suggested)
    # Sequence logic: start with influencer or technical_buyer (if signal is technical),
    # then economic_buyer. Avoid leading with exec unless signal is strategic.

    # Synthesis + drafting
    synthesis_outputs: Dict[str, SynthesisOutput]   # keyed by persona_id
    drafts: Dict[str, Draft]                         # keyed by persona_id

    # Cost tracking
    cost_metadata: CostMetadata

    # Error tracking
    errors: List[CompanyError]
    human_review_required: bool
    human_review_reasons: List[HumanReviewReason]

    # HITL override tracking
    override_requested: bool               # True if user chose "Override and generate anyway"
    override_reason: Optional[str]         # User-supplied reason for override (free text)
    drafted_under_override: bool           # True if draft was generated despite low confidence
    # Note: drafts generated under override ARE eligible for memory store (user explicitly approved)
    # but are tagged with drafted_under_override=True for future filtering

# === GLOBAL AGENT STATE ===

class AgentState(TypedDict):
    # Input
    target_companies: List[str]       # Raw company name strings (1–5)
    seller_profile: SellerProfile     # Required at session start; injected into Solution Mapping + Draft generation

    # Per-company isolated states (keyed by company_id)
    company_states: Dict[str, CompanyState]

    # Global orchestration
    pipeline_started_at: str          # ISO timestamp
    pipeline_completed_at: Optional[str]
    active_company_ids: List[str]
    completed_company_ids: List[str]
    failed_company_ids: List[str]

    # Human-in-the-loop flags
    awaiting_persona_selection: bool  # True when at least one company awaits HITL
    awaiting_review: List[str]        # company_ids needing human review

    # Execution metadata
    execution_log: List[str]          # Append-only log of agent actions
    total_cost_usd: float             # Sum across all companies

    # Final output
    final_drafts: List[Draft]         # All approved drafts (across companies/personas)
```

### 4.2 Capability Map Schema

The Capability Map is a vendor-agnostic, user-configurable JSON/YAML file that maps problem signals to solution categories.

```yaml
# capability_map.yaml
version: "1.0"
capabilities:
  - id: "data_platform_scalability"
    label: "Data Platform Scalability"
    keywords: ["data warehouse", "query performance", "petabyte", "data lakehouse"]
    problem_patterns:
      - "scaling data warehouse"
      - "slow query times on large datasets"
    solution_areas:
      - "Distributed query execution"
      - "Columnar storage optimization"
      - "Data lakehouse architecture"

  - id: "ml_infra"
    label: "ML Infrastructure"
    keywords: ["model training", "GPU", "model serving", "inference latency"]
    problem_patterns:
      - "deploying ML models at scale"
      - "GPU cost optimization"
    solution_areas:
      - "Managed model training"
      - "Inference optimization"
      - "MLOps platforms"
```

### 4.3 Memory Record Schema

```python
class MemoryRecord(TypedDict):
    record_id: str
    company_name: str
    persona_title: str
    signal_summary: str
    technical_context: str
    draft_subject: str
    draft_body: str
    approved_at: str          # ISO timestamp
    used_as_example: int      # Count of times injected as few-shot example
```

---

## 5. Agent Definitions

### 5.1 Orchestrator Agent

**Role**: Entry point. Validates input, initializes `AgentState`, and fans out per-company pipelines using `Send()`.

**Responsibilities**:
- Validate company list (1–5 entries, no duplicates)
- Normalize company names → `company_id` slugs
- Initialize per-company `CompanyState` objects
- Dispatch parallel `Send("company_pipeline", company_state)` for each company
- Aggregate results upon completion

**Inputs**: `target_companies: List[str]`
**Outputs**: Initialized `AgentState` with dispatched sub-pipelines

**Company Name Normalization Rules** (for `company_id` slug generation):
1. Lowercase all characters
2. Strip legal suffixes: "Inc", "Inc.", "LLC", "Ltd", "Corp", "Corporation", "Group" (case-insensitive)
3. Replace all non-alphanumeric characters with `-`
4. Collapse multiple consecutive `-` into one
5. Trim leading/trailing `-`

Examples: `"Stripe, Inc."` → `"stripe"`, `"Upbound Group"` → `"upbound"`, `"stripe.com"` → `"stripe-com"`

**Collision handling**: If two input names normalize to the same `company_id`, reject with error: "Duplicate company detected after normalization: [name1] and [name2] both resolve to [slug]. Please remove one."

**Constraints**:
- Hard limit: 5 companies
- Must not block on any single company pipeline

---

### 5.2 Signal Ingestion Agent

**Role**: Acquires raw signals for a single company using cost-tiered strategy.

**Responsibilities**:
- Execute Tier 1 signal acquisition (always)
- Evaluate Tier 1 signal density; escalate to Tier 2 if threshold not met
- Evaluate Tier 2 signal quality; escalate to Tier 3 only for high-confidence opportunities
- Record tier used, escalation rationale, and cost metadata

**Inputs**: `CompanyState` (company name)
**Outputs**: `CompanyState.raw_signals`, `CompanyState.cost_metadata` (updated)

**Tier Logic**:

| Tier | Trigger Condition | Sources |
|---|---|---|
| Tier 1 | Always | JSearch API (job postings), lightweight public signals |
| Tier 2 | Tier 1 signals < threshold OR signal ambiguity detected | Tavily web search, engineering blog scan |
| Tier 3 | Tier 2 confidence score ≥ high_confidence_threshold | Deep enrichment (configurable source) |

**Constraints**:
- Must log every escalation decision with reason
- Must update `cost_metadata` at each tier boundary

---

### 5.3 Signal Qualification Agent

**Role**: Scores raw signals and determines if they meet the threshold to proceed.

**Responsibilities**:
- Apply deterministic keyword weighting against `capability_map`
- Apply LLM-based severity assessment
- Compute composite score
- Mark signal as `qualified: true/false`
- If not qualified: set `signal_qualified = false`, skip remaining pipeline for this company

**Inputs**: `CompanyState.raw_signals`
**Outputs**: `CompanyState.qualified_signal`, `CompanyState.signal_qualified`

**Scoring Model**:

```
composite_score = (0.4 × deterministic_score) + (0.6 × llm_severity_score)
qualification_threshold = 0.45  # Configurable
```

**Score Definitions**:

| Score | Range | Computation Method |
|---|---|---|
| `deterministic_score` | 0.0–1.0 | Keyword overlap: (matched_keywords / total_capability_map_keywords) capped at 1.0 |
| `llm_severity_score` | 0.0–1.0 | LLM structured JSON output with 4 sub-dimensions (see below), averaged |
| `signal_ambiguity_score` | 0.0–1.0 | 1 − mean(recency_score, specificity_score) from LLM output |
| `composite_score` | 0.0–1.0 | Weighted combination above |

**LLM Severity Score Sub-dimensions** (each 0.0–1.0, averaged):
- `recency`: How recent is the signal? (within 7 days = 1.0, within 30 days = 0.7, older = lower)
- `specificity`: How specific to a technical pain? (generic hiring = 0.3, specific infra role = 0.8)
- `technical_depth`: Does the signal reference concrete technical concepts?
- `buying_intent`: Does the signal suggest active investment or evaluation?

**LLM Prompt Constraints**:
- Must assess signal against: recency, specificity, technical depth, buying intent
- Must output structured JSON: `{"recency": float, "specificity": float, "technical_depth": float, "buying_intent": float}`
- Any JSON parse failure → use deterministic score only with `partial: true` flag

---

### 5.4 Research Agent (Parallel Sub-Graph)

**Role**: Executes multiple research tasks in parallel for a qualified company.

**Sub-tasks** (all run concurrently):

| Sub-task | Description | Failure Behavior |
|---|---|---|
| Company Context | General market/company background | Graceful — partial result allowed |
| Tech Stack Extraction | Explicit technology mentions only (no inference) | Graceful — return empty list |
| Hiring Signal Analysis | Summarize hiring trends, growth areas | Graceful — partial result allowed |

**Inputs**: `CompanyState.qualified_signal`, `company_name`
**Outputs**: `CompanyState.research_result` (with `partial: bool`)

**Constraint**: Tech stack must only include explicitly stated technologies. No inferred or assumed technologies.

---

### 5.5 Solution Mapping Agent

**Role**: Maps the qualified signal and research context to vendor-agnostic solution areas using the Capability Map.

**Responsibilities**:
- Identify the core technical problem
- Match problem to capability map entries
- Assign confidence score (0–100)
- Output reasoning for transparency

**Inputs**: `CompanyState.qualified_signal`, `CompanyState.research_result`, `capability_map`
**Outputs**: `CompanyState.solution_mapping`

**Constraints**:
- Must NOT reference specific vendor products
- Must NOT hallucinate capability map entries
- Confidence score below 50 must flag `human_review_required = true`

**Confidence Score Scale Note**:
`SolutionMappingOutput.confidence_score` uses a **0–100 integer scale** (not 0–1) to make it human-readable in the UI. Two thresholds apply:
- `< 50` → flag `human_review_required = true` (low-confidence solution mapping warning)
- `< 60` → Draft Agent will not generate a draft (too uncertain to draft)

The 50–59 range is intentional: the system warns the user with a yellow badge while still proceeding to persona generation. The draft gate at 60 is stricter. This means a company with confidence 55 will: (a) show a yellow review badge, (b) generate personas for HITL selection, and (c) NOT produce a draft (user must override or manually outreach). This is by design — the review flag is informational; the draft gate is the hard stop.

---

### 5.6 Persona Generation Agent

**Role**: Generates 3 recommended personas for a company based on signal and solution mapping.

**Responsibilities**:
- Derive relevant buyer personas from solution areas and company context
- Generate `targeting_reason` for each persona
- Default to 3 personas unless fewer are clearly relevant

**Required Output Structure** (balanced buying group):

- **1 Economic Buyer** (budget owner — VP/Director level)
- **1 Technical Buyer** (owns implementation — Platform Lead, Architect)
- **1–2 Influencers** (practitioners / evaluators — IC or Manager level)
- **Optional: 1 Blocker** (e.g., Security, Procurement) — only if signal suggests procurement friction

**Signal → Persona Bias** (agent must apply these mapping rules):

| Signal Type | Expected Personas |
|---|---|
| Hiring (engineering roles) | Technical Buyer + 1–2 Influencers |
| Infra scaling | Technical Buyer + Economic Buyer |
| Cost optimization | Economic Buyer + FinOps Influencer |
| ML/AI signals | Head of AI (Economic Buyer) + ML Platform Lead (Technical Buyer) + Senior ML Engineer (Influencer) |
| Security/compliance signals | Blocker + Economic Buyer |

**Example (what “good” looks like)**:

Signal: *hiring ML infra engineers*
→ Head of AI *(economic_buyer, exec)* + ML Platform Lead *(technical_buyer, director)* + Senior ML Engineer *(influencer, ic)*

**Candidate Pool** (agent selects contextually from this pool):
- Head of Platform Engineering
- Director of Cloud Infrastructure
- FinOps Lead
- ML Platform Engineer
- VP of Engineering
- CTO / VP of Architecture
- Director of Data Engineering

**Inputs**: `CompanyState.solution_mapping`, `CompanyState.research_result`
**Outputs**: `CompanyState.generated_personas`

---

### 5.7 Persona Selection Gate (Human-in-the-Loop)

**Role**: Pauses pipeline execution to allow user to select, edit, or add personas.

**This is not an AI agent — it is a pipeline interrupt.**

**Behavior**:
- Pipeline emits `awaiting_persona_selection = true` to the UI
- UI presents `generated_personas` as a structured table with columns:

  | Persona | Role Type | Priority | Reason |
  |---|---|---|---|
  | ML Platform Lead | Technical Buyer | High | Owns implementation of ML infra |
  | Head of AI | Economic Buyer | Medium | Budget authority for AI platform spend |
  | Senior ML Engineer | Influencer | Low | Day-to-day practitioner pain point |

- **Default selection**: Top 1–2 personas (by `priority_score`) are pre-selected; user can override
- User actions allowed:
  - Select / deselect personas (checkbox)
  - Reorder personas (drag or up/down)
  - Edit persona title inline
  - Add a custom persona
  - Remove a generated persona
- On user confirmation, pipeline resumes with `selected_personas` populated

**Priority Score Logic** (computed by Persona Generation Agent):

| Criterion | Score Contribution |
|---|---|
| Direct ownership of the problem domain | High |
| Budget authority (economic buyer) | High |
| Indirect influence (evaluator / practitioner) | Medium |
| Peripheral / secondary role | Low |

**Constraint**: Pipeline must not proceed to Synthesis until user confirms persona selection.

---

### 5.8 Synthesis Agent

**Role**: Combines signal, research, solution mapping, and selected persona into a structured insight object.

**Responsibilities**:
- Run once per `(company, persona)` pair (parallel across personas)
- Produce structured `SynthesisOutput`

**Inputs**: `CompanyState.qualified_signal`, `CompanyState.research_result`, `CompanyState.solution_mapping`, selected `Persona`
**Outputs**: `CompanyState.synthesis_outputs[persona_id]`

**Output Fields**:
- `core_pain_point`: Specific technical pain (not generic)
- `technical_context`: What is known about their stack / architecture decisions
- `solution_alignment`: Which capability areas apply and why
- `persona_targeting`: Why this persona specifically cares about this problem
- `buyer_relevance`: Why THIS persona specifically would care — both business and technical angle (ties economic and technical motivation together)
- `value_hypothesis`: The outcome this persona is likely optimizing for (e.g., "reduce infra cost by 30%", "ship ML models faster")
- `risk_if_ignored`: What happens if they don't solve this — provides urgency signal without manufacturing fear

---

### 5.9 Draft Agent (with Confidence Gate)

**Role**: Generates outreach drafts per `(company, persona)` pair.

**Confidence Gate**:
- If `solution_mapping.confidence_score < 60`:
  - Do NOT generate draft
  - Set `human_review_required = true`
  - Add `HumanReviewReason.LOW_CONFIDENCE`

**Drafting Behavior**:
- Tone: Senior Solutions Architect — technically credible, not promotional
- **Persona-aware tone adaptation** (based on `Persona.role_type`):

  | Role Type | Focus | Depth |
  |---|---|---|
  | `economic_buyer` | Business impact, scale, cost, risk | Less technical detail |
  | `technical_buyer` | Architecture, tradeoffs, implementation path | Moderate-to-high depth |
  | `influencer` | Developer pain points, tooling friction, concrete examples | Practical, relatable |
  | `blocker` | Risk mitigation, compliance, stability, rollback posture | Cautious, evidence-based |

- Structure: Problem → technical context → solution alignment → call to action
- Avoid: Generic phrases ("I came across your company", "I hope this finds you well")
- Subject line: Must reference a specific signal or technical fact
- Inject 1–2 recent approved drafts as few-shot examples (from Memory Store)

**Inputs**: `CompanyState.synthesis_outputs[persona_id]`, `CompanyState.solution_mapping`, `AgentState.seller_profile`, memory examples
**Outputs**: `CompanyState.drafts[persona_id]`

**Seller Profile Injection**:
The `seller_profile` is injected into the draft prompt to bridge vendor-agnostic solution areas to the seller's specific products:
- `solution_areas` from Solution Mapping describe the problem space (vendor-agnostic)
- `seller_profile.portfolio_items` map those areas to the seller's actual products
- The prompt instructs the LLM: "The seller is from {seller_profile.company_name} and sells {portfolio_items}. Frame the solution alignment in terms of these specific products."
- If no seller profile is configured, the draft is generated in pure vendor-agnostic terms with a UI warning to add profile.

**Versioning**: Each regeneration increments `Draft.version`

---

### 5.10 Memory Agent

**Role**: Persists approved drafts for future retrieval and few-shot injection.

**Trigger**: Activated when user approves a draft in the UI.

**Responsibilities**:
- Write `MemoryRecord` to persistent store
- Index by company name and persona title
- Retrieve N most recent records for few-shot prompt injection

**Inputs**: Approved `Draft`, associated `SynthesisOutput`, `QualifiedSignal`
**Outputs**: Written `MemoryRecord`; retrieval API for Draft Agent

---

### 5.11 Chat Assistant Agent

**Role**: Answers follow-up questions about a selected company's pipeline state. Operates as a stateful conversational agent scoped to a single `CompanyState`.

**Responsibilities**:
- Respond to natural language queries about the selected company's signals, research, personas, and drafts
- Offer draft refinement suggestions (e.g., "make this more concise", "adjust tone for a CTO")
- Explain qualification and scoring decisions on request
- Suggest alternative personas not in the generated set

**Inputs**: Current `CompanyState` (read-only), user message, conversation history (last N turns)
**Outputs**: Text response (streamed to UI)

**Constraints**:
- Read-only access to `CompanyState` — cannot trigger pipeline re-runs directly
- Scoped to selected company only; cannot reason across multiple companies simultaneously
- Must not fabricate signals or research not present in `CompanyState`
- Draft edits suggested by the assistant are applied locally by the user, not auto-committed

**Context Injection**:
The agent receives a structured context block at the start of each turn:
```
Company: {company_name}
Signal Summary: {qualified_signal.summary}
Tech Stack: {research_result.tech_stack}
Core Problem: {solution_mapping.core_problem}
Selected Personas: {selected_personas}
Current Draft (if any): {drafts[active_persona_id]}
```

---

## 6. Execution Flow

### 6.1 Top-Level Flow

```
User Input (company names)
    │
    ▼
Orchestrator Agent
    │  validates input, initializes AgentState
    │
    ▼
    ├─── Send("company_pipeline", CompanyState_A)  ──▶ [Company A Pipeline]
    ├─── Send("company_pipeline", CompanyState_B)  ──▶ [Company B Pipeline]
    └─── Send("company_pipeline", CompanyState_C)  ──▶ [Company C Pipeline]

    (all run in parallel)
```

### 6.2 Per-Company Pipeline Flow

```
Signal Ingestion Agent
    │
    │  Tier 1 → evaluate → Tier 2? → evaluate → Tier 3?
    │
    ▼
Signal Qualification Agent
    │
    ├── [qualified = false] ──▶ STOP (mark company as SKIPPED)
    │
    └── [qualified = true]
            │
            ▼
        Research Agent (parallel sub-tasks)
            │  [graceful degradation on partial failure]
            │
            ▼
        Solution Mapping Agent
            │
            ├── [confidence < 50] ──▶ Flag human_review_required
            │
            ▼
        Persona Generation Agent
            │
            ▼
    ┌── HITL GATE: Persona Selection ──────────────────┐
    │   (pipeline pauses here)                         │
    │   User: select / edit / add personas             │
    └──────────────────────────────────────────────────┘
            │
            ▼
        Synthesis Agent (parallel — one per selected persona)
            │
            ▼
        Draft Agent (with Confidence Gate)
            │
            ├── [confidence < 60] ──▶ Skip draft, flag for review
            │
            └── [confidence ≥ 60] ──▶ Generate Draft

            ▼
    User Review in UI
            │
            ├── [Approve] ──▶ Memory Agent persists record
            ├── [Regenerate] ──▶ Draft Agent (version++)
            └── [Edit persona] ──▶ Synthesis + Draft Agent re-run
```

### 6.3 State Isolation Guarantee

Each company pipeline receives its own `CompanyState` copy dispatched via `Send()`. Agents write only to their scoped `company_id` key within `AgentState.company_states`. No shared mutable state exists between parallel company pipelines.

### 6.4 Pipeline Status Transitions

```
PENDING → RUNNING → AWAITING_HUMAN → RUNNING → COMPLETED
                                               → FAILED
                         │
                         └── SKIPPED (signal not qualified)
```

---

## 7. Signal Ingestion & Tiering

### 7.1 Tier 1 — Low Cost (Always Executed)

**Sources**:
- Job postings via JSearch API
  - Query: `{company_name} engineer` filtered to last 30 days
  - Extract: Role titles, required tech stack keywords, seniority distribution
- Other lightweight public signals (configurable)

**Signal Density Definition**:
Signal density = count of job postings where at least one capability map keyword matches the job title or description. A posting is "relevant" if `deterministic_score > 0`.

**Threshold for Tier 2 escalation** (any one condition triggers):
- Signal density < 3 (fewer than 3 relevant job postings found), OR
- `deterministic_score == 0` (no technology keywords matched against capability map), OR
- `signal_ambiguity_score > 0.7` (LLM scores signal as non-specific or stale)

### 7.2 Tier 2 — Moderate Cost (Conditional)

**Sources**:
- Tavily web search: `{company_name} engineering blog infrastructure OR platform`
- Engineering blog scan (last 90 days)
- Product announcements / changelog signals

**Threshold for Tier 3 escalation**:
- Tier 2 composite signal score ≥ 0.75, AND
- Company size / stage indicators suggest enterprise budget

### 7.3 Tier 3 — High Cost (Limited)

**Sources**:
- Deep enrichment APIs (configurable — e.g., firmographic data, funding signals)
- Only for companies passing Tier 2 threshold

**Constraint**: Tier 3 must be rate-limited at the session level to prevent runaway cost.

### 7.4 Cost Logging

Every tier transition must log:
- Tier entered
- Reason for escalation
- Estimated API cost
- Signals retrieved count

---

## 8. Solution Mapping

### 8.1 Capability Map Loading

- Loaded at startup from `capability_map.yaml`
- Hot-reloadable (no restart required)
- User can supply a custom capability map via settings

### 8.2 Matching Logic

1. Extract keywords from `QualifiedSignal.summary` and `ResearchResult`
2. Score each capability map entry by keyword overlap (deterministic)
3. LLM re-ranks and selects top 3 solution areas with reasoning
4. Confidence score reflects: keyword overlap + LLM certainty + signal specificity

### 8.3 Vendor-Agnostic Constraint

The Solution Mapping Agent must:
- Never output vendor product names (e.g., "Snowflake", "Databricks", "AWS Glue")
- Only output capability categories (e.g., "Columnar storage optimization", "Distributed query execution")
- The vendor application layer is the seller's responsibility, not the system's

---

## 9. UI Design

### 9.1 Layout Overview

The UI is a **workspace**, not a chat interface. It is organized into four primary panels:

```
┌─────────────────────────────────────────────────────────────────────┐
│  SignalForge                              [New Session] [Settings]  │
├───────────────────┬─────────────────────────────────────────────────┤
│                   │                                                 │
│  Company Table    │  [Tab: Insights] [Tab: Drafts]                 │
│  ─────────────    │                                                 │
│  □ LangChain  ✓   │  ┌──────────────────┬──────────────────────┐  │
│  □ Anthropic  ✓   │  │  Insights Panel  │  Draft Panel         │  │
│  □ Stripe     ⏳  │  │                  │                      │  │
│                   │  │  Signal Summary  │  [Persona: Head of   │  │
│  [+ Add Company]  │  │  Core Problem    │   Platform Eng]      │  │
│                   │  │  Tech Context    │                      │  │
│  Persona Table    │  │  Solution Areas  │  Subject: [...]      │  │
│  ─────────────    │  │  Confidence: 82  │  Body: [...]         │  │
│  Head of Plat..   │  │                  │                      │  │
│  Dir. Cloud Inf   │  └──────────────────│  [Copy] [Regenerate] │  │
│  [+ Add Persona]  │                     └──────────────────────┘  │
│                   │                                                 │
├───────────────────┴─────────────────────────────────────────────────┤
│  Chat Assistant                                          [Expand]   │
│  > Ask anything about the selected company or draft...              │
└─────────────────────────────────────────────────────────────────────┘
```

### 9.2 Company Table

**Columns**:
- Company Name
- Signal Status (qualified / not qualified / pending)
- Pipeline Status (running / awaiting input / completed / failed)
- Confidence Score (badge)
- Action (view details)

**Behaviors**:
- Filterable by status
- Row selection loads insights/drafts for that company in right panel
- Color-coded status badges

### 9.3 Persona Table

- Shows personas for the currently selected company
- Inline editing of persona titles (click to edit)
- Add custom persona via `[+ Add Persona]` button
- Remove persona via row delete
- Persona row selection switches draft panel to that persona's draft

### 9.4 Insights Panel

Displays for selected `(company, persona)`:
- Signal summary
- Core pain point
- Technical context
- Solution areas (as tags)
- Confidence score (numeric + visual indicator)

Read-only. No editing of insights.

### 9.5 Draft Panel

Displays for selected `(company, persona)`:
- Subject line (editable inline)
- Body (editable inline)
- Version indicator (v1, v2, etc.)
- [Copy to Clipboard] button — one-click, no confirmation required
- [Regenerate] button — re-runs Draft Agent for this pair
- [Approve] button — triggers Memory Agent persistence

**Behaviors**:
- Inline edits are local (do not re-trigger agents)
- Regenerate increments version and replaces current draft

### 9.6 Chat Assistant Panel

- Collapsed by default (expandable)
- Scoped to the currently selected company
- Supports:
  - "Refine this draft to be more concise"
  - "What other personas should I target?"
  - "Explain why this signal was qualified"
  - Follow-up questions about research results
- Chat assistant has access to the current `CompanyState` as context

### 9.7 Progress Indicators

- Per-company pipeline progress bar (5 stages)
- Stage labels: Signals → Qualifying → Researching → Mapping → Generating
- Spinner on active stage
- HITL gate shown as pause indicator with prompt for user action

### 9.8 Human Review Flag

When `human_review_required = true`:
- Company row shows a yellow warning badge
- Insights panel shows review reason and explanation
- Draft panel shows "Draft not generated — confidence too low" with option to:
  - Override and generate anyway (sets `override_requested = true`, prompts for optional `override_reason`)
  - Flag for manual outreach

### 9.9 Settings Panel

Accessible via `[Settings]` button in the header.

**Tabs**:
- **Seller Profile**: Edit `company_name`, `portfolio_summary`, `portfolio_items`
- **API Keys**: Configure and test JSearch, Tavily, and LLM provider keys
- **Session Budget**: Edit session spend cap (default $0.50), Tier 3 call limit
- **Memory Store**: Browse, delete, or export approved drafts (see Section 12.3)

### 9.10 All-Companies-Skipped State

If all submitted companies fail signal qualification:
- Company Table shows all rows with "No Signal" badge
- Right panel shows: "No actionable signals found. Try different companies, or lower the qualification threshold in Settings."
- Suggests: link to documentation on qualifying companies
- Session cost is logged (Tier 1 costs still apply)

---

## 10. Cost Strategy

### 10.1 Principles

1. **Progressive enrichment**: Never escalate to a higher tier without evidence from the lower tier
2. **Fail cheaply**: If Tier 1 yields no signal, skip company rather than spend on Tier 2
3. **Track everything**: Every API call logs cost metadata
4. **Session budget**: Configurable max spend per session (default: $0.50 USD)

### 10.2 Cost Budget Controls

| Control | Default | Configurable |
|---|---|---|
| Max companies per session | 5 | Yes |
| Session spend cap | $0.50 | Yes |
| Tier 3 calls per session | 1 | Yes |
| LLM calls per company | ~8–12 | No |

### 10.3 Cost Display

- Per-company estimated cost shown in Company Table (tooltip)
- Session total shown in header
- Warning when session budget is 80% consumed

### 10.4 Cost Estimation Model

| Operation | Estimated Cost |
|---|---|
| JSearch API call | $0.001–$0.005 |
| Tavily web search (per query) | $0.01–$0.02 |
| LLM call (qualification + scoring) | $0.005–$0.02 |
| LLM call (synthesis + draft) | $0.01–$0.04 |
| Tier 3 enrichment (per company) | $0.05–$0.15 |

---

## 11. Error Handling & Fault Tolerance

### 11.1 Per-Stage Error Classification

| Error Type | Behavior |
|---|---|
| Signal source unavailable | Log error, attempt fallback source, continue with partial |
| Signal qualification failure (LLM error) | Use deterministic score only, mark as partial |
| Research sub-task failure | Continue with partial `ResearchResult` (`partial: true`) |
| Solution mapping failure | Flag `human_review_required`, skip draft |
| Persona generation failure | Use default persona pool as fallback |
| Draft generation failure | Mark draft as failed, show error in UI |
| Memory write failure | Log error, non-blocking (pipeline continues) |

### 11.2 Graceful Degradation Rules

- Any single sub-task failure in the Research Agent must not block the main pipeline
- A company pipeline failing must not affect other parallel company pipelines
- All errors are stored in `CompanyState.errors` for UI display

### 11.3 Retry Policy

- Signal source calls: 2 retries with exponential backoff
- LLM calls: 1 retry on rate limit, 0 retries on content errors
- No infinite retry loops

### 11.4 User-Facing Error States

- Each failed company shows error badge in Company Table
- Error detail accessible via "View Details" in Company row
- User can manually retry a failed stage

---

## 12. Memory & Feedback System

### 12.1 Storage

- Persistent store (SQLite or equivalent)
- Schema: `MemoryRecord` (see Section 4.3)
- Write on: user approves a draft
- Index on: `company_name`, `persona_title`, `approved_at`

### 12.2 Retrieval for Few-Shot Injection

- Draft Agent queries memory store before generating a draft
- Retrieves up to 2 most recent approved drafts
- Injects as examples in system prompt
- Helps maintain tone consistency and quality over time

### 12.3 Memory Browsing (UI)

- Accessible via Settings → Memory Store
- View all approved drafts
- Delete individual records
- Export as CSV

---

## 13. Testing Strategy

### 13.1 Unit Tests

| Component | What to Test |
|---|---|
| Signal Qualification Agent | Deterministic scoring with known keyword inputs |
| Confidence gate | Boundary values: 59, 60, 61 |
| Capability map loader | Valid YAML, missing fields, malformed entries |
| Cost metadata accumulator | Correct aggregation across tier transitions |
| Orchestrator | Company limit enforcement, slug normalization |

### 13.2 Integration Tests

| Scenario | Expected Behavior |
|---|---|
| 5 companies in parallel | All 5 complete without state collision |
| 1 company with all Tier 1 signals | No Tier 2 calls made |
| Signal qualification fails (score < threshold) | Company skipped, rest continue |
| Partial research failure | `ResearchResult.partial = true`, pipeline continues |
| Low confidence score | Draft not generated, `human_review_required = true` |
| User adds custom persona | Synthesis + Draft run for custom persona |

### 13.3 End-to-End Tests

- Full pipeline run against mock company data (LangChain fixture)
- HITL gate: verify pipeline pauses, resumes correctly after simulated user input
- Memory injection: verify prior approved drafts appear in new draft prompts
- Cost budget: verify pipeline halts at session spend cap

### 13.4 LLM Evaluation

| Eval Dimension | Method |
|---|---|
| Draft technical credibility | LLM-as-judge rubric (not generic, specific signal referenced) |
| Draft tone adherence | LLM-as-judge rubric (no generic phrases) |
| Solution mapping accuracy | Human-labeled test set (20 companies) |
| Signal qualification recall | Precision/recall against labeled signal set |

### 13.5 Test Data

- Maintain a fixture library of 10 canonical companies with known signals
- Each fixture includes: expected tier used, expected qualification result, expected solution areas
- Fixtures stored in `tests/fixtures/`

---

## 14. Risks & Limitations

### 14.1 Signal Quality

| Risk | Severity | Mitigation |
|---|---|---|
| Job postings lag real intent by 2–4 weeks | Medium | Supplement with blog/web signals in Tier 2 |
| Signal sources go offline / rate-limit | High | Graceful degradation + fallback source config |
| False positives in signal qualification | Medium | Tunable thresholds + human review flag |
| Low signal density for small companies | Medium | Skip instead of hallucinate — explicit empty state |

### 14.2 LLM Reliability

| Risk | Severity | Mitigation |
|---|---|---|
| LLM hallucinates tech stack details | High | Tech stack extraction: explicit mentions only, no inference |
| LLM outputs vendor names in solution mapping | Medium | System prompt constraint + output validation |
| Draft tone degrades without memory examples | Low | Memory injection; periodic few-shot refresh |
| LLM structured output fails (malformed JSON) | Medium | Retry with stricter schema prompt; fallback to partial |

### 14.3 Cost & Performance

| Risk | Severity | Mitigation |
|---|---|---|
| Runaway cost on 5 parallel Tier 3 calls | High | Session budget cap; Tier 3 rate limit per session |
| Slow pipeline (>90 seconds for 5 companies) | Medium | Parallel execution; streaming progress updates |
| API rate limits on signal sources | Medium | Retry with backoff; configurable rate limits |

### 14.4 Data & Privacy

| Risk | Severity | Mitigation |
|---|---|---|
| Storing sensitive draft content | Medium | Memory store is local by default; no cloud sync unless opted in |
| Scraping signals from restricted sources | High | Only use APIs with explicit TOS for programmatic access |

### 14.5 Known Limitations

- Maximum 5 companies per session (hard limit by design)
- Tech stack extraction is explicit-only; will not infer from indirect signals
- System is vendor-agnostic; seller must apply their own product positioning
- Memory store is local per-user; not shared across team members in v1
- Chat assistant is scoped per company; no cross-company reasoning

---

## 15. Success Criteria

The system is considered successful when a user can:

1. **Input** up to 5 company names and trigger automated parallel processing
2. **Observe** real, technically grounded signals for each company (not generic summaries)
3. **Understand** the specific technical problem identified for each company
4. **See and modify** recommended personas (select, edit, add) before outreach is generated
5. **Receive** outreach drafts that:
   - Reference a specific signal or technical fact
   - Map the problem to a solution area credibly
   - Are written in a senior technical voice, not a generic sales voice
6. **Copy** a draft to clipboard with a single click
7. **Trust** the system — no hallucinated tech stacks, no generic claims, clear confidence scores
8. **Iterate** — regenerate drafts for different personas, refine via chat assistant
9. **Stay within budget** — session cost stays within configured cap
10. **Persist value** — approved drafts improve future draft quality via memory injection

---

---

## 16. Consultation Log

### Iteration 1 (2026-03-26) — Codex + Claude review (Gemini rate-limited)

**Codex verdict**: REQUEST_CHANGES
**Claude verdict**: COMMENT

**Changes made in response to consultation feedback:**

| Issue | Source | Change Made |
|---|---|---|
| Scoring computations under-specified | Codex | Added score definitions table + LLM sub-dimensions in Section 5.3 |
| `signal_ambiguity_score` undefined | Codex | Defined as `1 - mean(recency, specificity)` in Section 5.3 |
| "Signal density" undefined | Codex | Added explicit definition in Section 7.1 |
| HITL override semantics not in state | Codex | Added `override_requested`, `override_reason`, `drafted_under_override` to CompanyState |
| Mixed confidence scale (0–1 vs 0–100) | Codex | Added "Confidence Score Scale Note" in Section 5.5 documenting the intentional difference |
| Two confidence thresholds (50/60) unclear | Codex + Claude | Documented the 50–59 interaction explicitly in Section 5.5 |
| Seller Profile not in Draft Agent inputs | Claude | Added explicit input and prompt injection strategy in Section 5.9 |
| Session lifecycle undefined | Claude | Added Section 3.4 (Session Lifecycle) |
| API key management absent | Claude | Added Section 3.5 (Authentication & API Key Management) |
| Seller Profile setup flow missing from UI | Claude | Added Settings Panel in Section 9.9 |
| Company name normalization rules undefined | Claude | Added normalization rules + collision handling in Section 5.1 |
| "All companies skipped" UX undefined | Claude | Added Section 9.10 |
| Fallback source configuration | Codex | Noted as implementation detail (configurable in Tier definitions); not added to spec (deferred to plan) |
| LLM call budget inconsistency | Codex | Noted; cost strategy Section 10.2 now defers to plan for exact budget enforcement |
| Chat Assistant → draft edit acceptance | Claude | Documented as copy-paste in Section 5.11 (intentional v1 constraint) |

**Not addressed (deferred to Plan phase):**
- Exact LLM call budget enforcement mechanism (implementation detail)
- Data retention policy beyond v1 (out of scope for v1)
- Rate-limit abuse protection (out of scope for local-first v1)
- Performance testing specifics (will be in plan)

---

*End of Specification — Spec 1: Proactive Sales Signal Intelligence Engine*

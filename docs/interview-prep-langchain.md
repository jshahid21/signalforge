# LangChain Interview Prep — SignalForge Reference

> For the Deployed Engineer role at LangChain.
> This doc teaches the concepts first, then gives you interview answers.
> Every concept is tied to real code in SignalForge so you can look at it.

---

## Part 1: The LangChain Universe — What Are All These Things?

LangChain has several products. Here's what each one is in plain English:

| Product | What It Is | Analogy |
|---------|-----------|---------|
| **LangChain** (the library) | Python/JS toolkit for working with LLMs — send prompts, get responses, parse output | Like `requests` is for HTTP, LangChain is for LLMs |
| **LangGraph** | A way to build multi-step AI workflows as a "graph" (more on this below) | Like an assembly line where each station does one job |
| **LangSmith** | Dashboard for monitoring, testing, and debugging your LLM apps | Like Datadog but specifically for AI apps |
| **LangGraph Platform** (now called "LangSmith Deployment") | Managed hosting for running LangGraph apps in production | Like Heroku/Vercel but for AI agent backends |

**In SignalForge, we use:**
- **LangChain** → to talk to Claude and GPT-4o (send prompts, get responses)
- **LangGraph** → to orchestrate our 8-stage pipeline
- **LangSmith** → for evaluating draft quality (optional, not required to run)
- **LangGraph Platform** → not yet, but our `langgraph.json` config is ready for it

---

## Part 1b: What SignalForge Actually Does

SignalForge is an AI-powered sales signal intelligence engine. You give it company
names, and it runs an 8-stage pipeline that ends with persona-targeted outreach emails.
Here's what each stage does and why it matters:

**1. Signal Ingestion** — Searches for buying signals (job postings, web articles)
using a cost-tiered system. Tier 1 starts cheap with JSearch job postings (~$0.001/call).
If too few signals come back, it escalates to Tier 2 using Tavily web search (~$0.015/call).
This keeps costs low when signals are easy to find.

**2. Signal Qualification** — Scores signals using a hybrid approach: 40% deterministic
keyword matching against your capability map + 60% LLM-assessed severity (recency,
specificity, technical depth, buying intent). A composite threshold of 0.45 filters noise.
If the LLM fails, it falls back to keyword-only scoring.

**3. Research** — Gathers company context: what the company does, their tech stack,
hiring trends. Three sub-tasks run concurrently using the LLM.

**4. Solution Mapping** — Maps the signal to vendor-agnostic solution areas. Not "they
need your product" but "they have a container orchestration scaling problem that maps
to platform engineering." This keeps the analysis honest. Confidence score (0-100) gates
downstream behavior.

**5. Persona Generation** — Creates 2-4 buyer personas based on signal type. Hiring
signals → technical buyers and influencers. Cost signals → economic buyers. Security
signals → blockers. Each persona gets a priority score for outreach sequencing. LLM
customizes titles per company; falls back to templates if LLM fails.

**6. HITL Gate** — Pipeline **pauses** here. You review personas, edit titles, add
custom personas, remove ones that don't fit. Only confirmed personas proceed. This is
where human judgment matters most.

**7. Synthesis** — Generates deep per-persona insights: core pain point, technical
context, buyer relevance. This is the bridge between the signal and the email.

**8. Draft Generation** — Writes the actual email. Confidence-gated:
- Score < 35 → draft skipped entirely (signal too weak)
- Score 35-60 → hedged, exploratory tone
- Score ≥ 60 → full solution pitch with seller context

Tone adapts to persona type — economic buyers get ROI framing, technical buyers get
architecture language, influencers get pain-point narratives, blockers get risk
mitigation framing.

**Also includes:**
- **Seller Intelligence** — auto-scrapes your company website for differentiators,
  sales plays, proof points, and competitive positioning. Injected into draft generation.
- **Chat Assistant** — per-company Q&A with streaming responses. Has full context on
  signals, personas, and drafts.
- **Memory** — approved drafts are stored and used as few-shot examples for future
  sessions, keeping tone consistent.
- **Cost Control** — $0.50 default budget per session. Budget warnings at 75%. Per-stage
  cost tracking. Every LLM call checks budget before executing.

---

## Part 2: LangGraph Concepts — From Zero

### What is a "graph"?

A graph is just **boxes connected by arrows**. Each box does something. The arrows say "go here next."

In SignalForge, our graph looks like this:

```
[Orchestrator] → [Signal Ingestion] → [Signal Qualification] → [Research]
    → [Solution Mapping] → [Persona Generation] → [HITL Gate] → [Done]
```

That's 7 boxes (called **nodes**) connected by arrows (called **edges**).
Each pipeline stage is its own node, so when the graph runs, it fires a
streaming event at every stage boundary — this is how our progress bar works.

**Where in the code:** `backend/pipeline.py` lines 221-240

```python
graph = StateGraph(AgentState)

graph.add_node("orchestrator", orchestrator_node)
graph.add_node("signal_ingestion", signal_ingestion_node)
graph.add_node("signal_qualification", signal_qualification_node)
graph.add_node("research", research_node)
graph.add_node("solution_mapping", solution_mapping_node)
graph.add_node("persona_generation", persona_generation_node)
graph.add_node("hitl_gate", hitl_gate_node)

graph.set_entry_point("orchestrator")
graph.add_edge("orchestrator", "signal_ingestion")
graph.add_edge("signal_ingestion", "signal_qualification")
graph.add_edge("signal_qualification", "research")
graph.add_edge("research", "solution_mapping")
graph.add_edge("solution_mapping", "persona_generation")
graph.add_edge("persona_generation", "hitl_gate")
graph.add_edge("hitl_gate", END)
```

### What is "state"?

State is **the data that flows through the graph**. Every box can read it and update it.

Think of it like a shared clipboard. The orchestrator writes company names on it. The company pipeline reads those names, does work, and writes results back. The HITL gate reads those results to see if any company needs human input.

**Where in the code:** `backend/models/state.py` lines 203-228

Our state (`AgentState`) includes things like:
- `company_states` — results for each company (signals, personas, drafts)
- `total_cost_usd` — how much money we've spent on API calls
- `awaiting_persona_selection` — do we need the user to pick personas?

### What is a "node"?

A node is just **a Python function** that:
1. Receives the current state
2. Does some work
3. Returns updates to the state

Example: our orchestrator node receives the state, reads the company names, and prepares them for processing.

**Where in the code:** `backend/agents/orchestrator.py` (the `orchestrator_node` function)

### What is an "edge"?

An edge is an arrow saying **"after this node finishes, go to that node next."**

A **conditional edge** is an arrow that says "after this node, **decide** where to go based on some logic." In our case, the orchestrator uses a conditional edge to dispatch companies.

### What is `Send()`? (and why we moved away from it)

`Send()` is LangGraph's way to do **parallel processing**. Instead of going
to one next node, you send **multiple copies** of work to the same node.

**Our original design:** The orchestrator created 5 `Send()` objects — one per
company — and LangGraph ran all 5 copies of `company_pipeline` in parallel.

```python
# OLD APPROACH (we no longer use this)
def dispatch_companies(state):
    sends = []
    for company_id, company_state in state["company_states"].items():
        sends.append(Send("company_pipeline", {
            "company_state": company_state,
        }))
    return sends  # LangGraph runs all at the same time
```

**The problem with Send() — explained simply:**

LangGraph has a "save game" feature called a checkpointer. It saves the state
of the graph after each step, so you can pause and resume later. This is how
human-in-the-loop is supposed to work — pause the graph, wait for the human,
resume from the saved state.

But the saved state needs to be converted to data that can be stored (like
JSON). `Send()` objects are **Python objects in memory** — they contain
function references and complex data that can't be cleanly converted to JSON.

**It's like trying to photocopy a live phone call.** You can photocopy a
piece of paper (regular data), but you can't photocopy an ongoing conversation
(a Send object). The checkpointer tries to "photocopy" the entire graph state,
including the Send objects, and it fails.

**Our new design:** Instead of Send(), each stage is a separate graph node.
Inside each node, all companies run in parallel using Python's `asyncio.gather()`.

```python
# NEW APPROACH — each stage node processes all companies in parallel
async def signal_ingestion_node(state):
    active_companies = [...]  # filter companies ready for this stage
    results = await asyncio.gather(*[      # run all at once
        run_signal_ingestion(cs) for cs in active_companies
    ])
    return merged_results
```

**Why this is better:**
1. No Send objects = no serialization problem
2. Each stage is a real graph node = `astream()` fires at every boundary
3. LangGraph Studio shows the full 7-node pipeline visually
4. Parallel processing still happens — just inside each node instead of across nodes
5. The checkpointer could work now (no Send objects to serialize)

### What are "reducers"?

Here's the problem with parallel processing: if 5 companies run at the same time, and they all try to update `total_cost_usd`, who wins?

**Reducers** are rules for how to merge results from parallel branches.

```python
total_cost_usd: Annotated[float, operator.add]
```

This says: "when multiple branches return cost, **add them up**."

Other reducers we use:
- `operator.concat` → combine lists (list of failed companies from each branch)
- `merge_dict` → merge dictionaries (each company writes to its own key)
- `lambda a, b: a or b` → if ANY branch says "awaiting human input," the answer is yes

**Where in the code:** `backend/models/state.py` lines 209-227

**Plain English:** "Reducers are the rules for combining results when multiple things run at the same time. Add up costs, combine lists, merge dictionaries."

### What is a "checkpointer"?

A checkpointer **saves the state of the graph** after each step, like a save point in a video game. If something crashes, you can reload from the last save.

LangGraph offers several:
- `MemorySaver` — saves in memory (lost when app restarts)
- `SqliteSaver` — saves to a SQLite database
- `PostgresSaver` — saves to Postgres (production-grade)

**In SignalForge:** We tried using checkpointers but hit a problem (explained in Part 3). We save session state ourselves using our own SQLite code instead.

### What is "streaming"?

When you run a graph, you can **watch it execute** step by step instead of waiting for the whole thing to finish.

LangGraph has 6 streaming modes:
- `values` — see the full state after each node
- `updates` — see just what changed at each node
- `messages` — see LLM tokens as they're generated (like ChatGPT's typing effect)
- `tasks` — see when each task starts and finishes
- `custom` — your nodes can emit any data they want during execution
- `checkpoints` — see each saved state

**In SignalForge:** We use `graph.astream()` in `backend/api/routes/sessions.py` line 117, but because our entire company pipeline is one big node, we only get one update per company (when it finishes). This is the progress bar issue we found.

### What is the "Functional API"?

LangGraph has **two ways** to build workflows:

1. **StateGraph API** (what we use) — you define nodes and edges explicitly
2. **Functional API** (newer) — you write normal Python functions with special decorators

The Functional API uses:
- `@entrypoint` — marks the main function (like `def main()`)
- `@task` — marks a unit of work (like each stage in our pipeline)
- `interrupt()` — pauses and waits for user input
- `Command` — resumes from where you paused

**You can use both in the same app.** For example, you could keep the StateGraph for the main pipeline but use `@entrypoint`/`@task` for a specific flow like HITL.

**In SignalForge:** We don't use the Functional API yet, but it could solve our HITL problem (see Part 3).

---

## Part 3: Three Decisions We Made (and Why) — Your Interview Stories

These are the stories you'll tell in interviews. Each one shows you understand
trade-offs, not just features.

### Story 1: "How we handle parallel processing and how the design evolved"

**The situation:** A user enters 5 company names. Processing each takes 30-60 seconds (multiple LLM calls, API searches). Running them one by one = 3-5 minutes of waiting.

**Version 1 — Send():** We used LangGraph's `Send()` to dispatch all 5 companies
simultaneously, each running the entire pipeline independently. The challenge
was merging results — we used Annotated reducers (`operator.add` for costs,
`merge_dict` for per-company state) to safely combine parallel branches.

**The problem:** Send() worked for parallelism, but broke human-in-the-loop.
When the graph paused and tried to save state, the checkpointer couldn't
serialize the Send objects (see Story 2). Also, the entire per-company pipeline
was one big node, so streaming only fired once per company — the progress bar
didn't update in real-time.

**Version 2 — separate nodes with asyncio.gather():** We refactored the graph
from 3 nodes to 7 — each pipeline stage is its own node. Inside each node,
all companies run in parallel using Python's `asyncio.gather()`. This gives
us:
- Real-time streaming (astream fires at every node boundary)
- No Send objects (no serialization issue)
- Same parallel performance (gather runs companies concurrently within each stage)

The reducers are still there — costs still add up, company states still merge
correctly — but now they work within each node's return, not across Send
branches.

**Look at:** `backend/pipeline.py` (the 7-node graph + `_run_stage_node()` helper) and `backend/models/state.py` (the reducers)

---

### Story 2: "Why our human-in-the-loop gate lives outside the graph"

**The situation:** After generating personas, we want the user to review and
select which ones to target before generating emails. The pipeline needs to
**pause** and **wait** for human input.

**What LangGraph offers:** `interrupt()` — it pauses the graph and saves state
via a checkpointer. When the user responds, you resume from where you left off.

**What went wrong (in our original Send-based design):** When you resume,
LangGraph tries to re-run the orchestrator's dispatch function, which produced
`Send()` objects. The checkpointer needs to save these to disk so it can
restore them later. But `Send()` objects contain Python function references
and complex data that **can't be converted to JSON or stored in a database**.

**Think of it like a bookmark.** A checkpointer is like putting a bookmark in
a book so you can come back to the same page. But `Send()` objects are like
sticky notes with live phone numbers that stop working when you close the book.
When you reopen the book, the phone numbers are dead — the resume crashes.

**What we did instead:** The graph runs all the way through and exits. The
`hitl_gate` node sets a flag: "these companies need persona selection." Our
REST API handles the pause:
1. Frontend shows the persona picker
2. User selects personas
3. API calls synthesis and draft generation **directly** — no graph re-entry

**Why this is actually good:** The graph handles computation. The API handles
user interaction. Clean separation of concerns.

**Note:** After refactoring to separate nodes (Story 3), we no longer use
Send() at all. The checkpointer serialization issue is gone. We could now
explore using `interrupt()` for HITL since there are no Send objects in the
state. Or we could use the Functional API's `@entrypoint`/`@task` pattern
where each task result is individually saved. Both approaches could bring
HITL back into the graph — this is future work.

**Look at:** `backend/agents/hitl_gate.py` (the gate) and `backend/api/routes/personas.py` (the resume outside the graph)

---

### Story 3: "Why the progress bar was stuck and how we fixed it with graph design"

**The situation:** Each company has a 5-stage progress bar (Signals →
Qualifying → Researching → Mapping → Generating). But it never moved — it
stayed on the first stage until everything finished, then jumped to done.

**Root cause:** Our original `company_pipeline` function ran all 8 stages
inside **one LangGraph node**. LangGraph's streaming (`astream()`) only fires
events at **node boundaries** — when one node finishes and the next starts.
Since the whole company flow was one node, there was only one event: "company
finished."

**Think of it like a factory floor.** Imagine a factory where all 5 assembly
stations are in one room with no walls. A supervisor standing outside can only
tell you "the room is busy" or "the room is done." Now put walls between each
station with windows. The supervisor can see: "Station 1 done, Station 2
working, Stations 3-5 waiting." That's what splitting nodes does — it gives
the streaming system walls to report on.

**What we did:** Refactored the graph from 3 nodes to 7. Each pipeline stage
is its own node:

```
orchestrator → signal_ingestion → signal_qualification → research
    → solution_mapping → persona_generation → hitl_gate → END
```

Now `astream()` fires automatically at every stage boundary. The progress bar
updates in real-time with no extra code — it just reads the events that
LangGraph naturally emits between nodes.

Inside each node, all companies still run in parallel via `asyncio.gather()`,
so we didn't lose any performance.

**Other approaches we considered:**
- `stream_mode="custom"` — lets you manually emit events from inside a node
  (like adding intercoms between stations). Would work but it's a workaround.
- Functional API `@task` with `stream_mode="tasks"` — tasks auto-emit
  start/finish events. Cleaner but requires rewriting to the Functional API.

We went with separate nodes because it uses LangGraph as designed, gives the
best Studio visualization, and also eliminated the Send() serialization issue.

**Look at:** `backend/pipeline.py` (7-node graph + `_run_stage_node()` helper) and `frontend/src/components/ProgressBar.tsx`

---

## Part 4: LangSmith — What It Is and How We Use It

### What is LangSmith?

LangSmith is a **dashboard for AI apps**. It shows you:
- Every LLM call your app makes (what you sent, what came back, how long it took)
- How much each call cost (tokens used)
- Whether users liked the output (feedback)
- Test results over time (evaluations)

### How we use it today

**Evaluation only.** We have an LLM-as-judge test that scores our email drafts on three criteria:
1. Does it sound technically credible? (not salesy)
2. Does the tone match the persona? (executive vs. engineer)
3. Does it avoid generic phrases? ("I hope this email finds you well")

This runs separately from our regular tests. It's in `tests/eval/draft_eval.py`.

### What we'd add next (and why it matters)

**1. Production tracing** (Issue #31)
Turn on tracing so every LLM call in the pipeline shows up in the LangSmith dashboard. You just set two environment variables:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key
```
LangChain's LLM wrappers (ChatAnthropic, ChatOpenAI) automatically report to LangSmith when these are set. Zero code changes in your agents.

**2. Structured trace trees** (Issue #32)
Add `@traceable` decorators to each agent function. Without this, you just see flat LLM calls. With it, you see a tree: Pipeline → Company → Signal Ingestion → LLM Call. Much easier to debug "why was this company slow?"

**3. Feedback from users** (Issue #33)
When someone approves a draft → log positive feedback to LangSmith.
When someone regenerates (rejects) → log negative feedback.
Now you can see: "80% of drafts for technical buyers get approved, but only 40% for economic buyers." That tells you which prompts need work.

**4. Datasets from real usage** (Issue #34)
Approved drafts become test examples. After a prompt change, run the eval against real approved drafts to check for regressions. This is the **flywheel**: approve → dataset → eval → improve prompt → better drafts → more approvals.

---

## Part 5: LangGraph Platform — What a Deployed Engineer Would Work On

LangGraph Platform (now called **LangSmith Deployment**) is managed infrastructure for running LangGraph apps. This is probably core to the role you're interviewing for.

### What it does

When you run LangGraph locally, you have:
- Your own server process
- State saved in memory or local SQLite
- If it crashes, everything is lost

LangGraph Platform adds:
- **Task queues** — requests don't get lost under heavy load
- **Horizontal scaling** — multiple workers handle requests in parallel
- **Postgres checkpointing** — state survives crashes and restarts
- **Built-in streaming** — real-time events from background workers
- **Cron jobs** — scheduled agent runs

### Deployment options

| Option | What It Means | Who It's For |
|--------|--------------|--------------|
| **Self-Hosted Lite** | Free, run it yourself, up to 1M node executions | Developers, small teams |
| **Cloud SaaS** | LangChain hosts everything | Teams that don't want to manage infra |
| **BYOC** | Runs in YOUR cloud (AWS/GCP), LangChain manages it | Enterprise with data requirements |
| **Self-Hosted Enterprise** | Fully on your infra | Maximum control |

### How SignalForge connects

Our `langgraph.json` file registers the pipeline:
```json
{
  "graphs": {
    "signalforge": "./backend/pipeline.py:build_pipeline"
  }
}
```

This means:
- **LangGraph Studio** (desktop app) can open our project and visually step through the pipeline
- **LangGraph Platform** could deploy our pipeline as a managed service
- We'd get Postgres checkpointing, task queues, and horizontal scaling "for free"

### What would change if we deployed on the platform

1. **Checkpointing works** — Postgres checkpointer is more robust, and the platform team is actively working on serialization improvements (our Send() issue might be solved)
2. **No need for our custom WebSocket** — the platform has built-in streaming with all 6 modes
3. **No need for our background task** — the platform's task queue handles long-running pipelines
4. **Horizontal scaling** — multiple pipelines can run simultaneously without us managing workers

---

## Part 6: Recruiter Questions (60-90 second answers)

### Q: Tell me about yourself and a project you're proud of.

> "I built SignalForge, an AI-powered sales intelligence engine. It takes company
> names, discovers buying signals from job boards and web sources, and generates
> targeted outreach emails.
>
> What I'm most proud of is the pipeline architecture. It processes multiple companies
> in parallel using LangGraph, with real-time progress updates via WebSocket. There's a
> human-in-the-loop gate where users pick which personas to target before any emails
> are written. And every stage has graceful fallback — if an LLM call fails, the
> pipeline degrades instead of crashing.
>
> I used LangGraph for orchestration, LangSmith for draft quality evaluation, and
> built it as a full-stack app with React and FastAPI."

### Q: Why LangChain?

> "I chose LangGraph because I needed parallel execution with safe state management.
> Five companies running at the same time, each making multiple LLM calls, and I need
> their costs to add up correctly and their results to not overwrite each other. LangGraph's
> reducers handle that elegantly.
>
> I also see where the ecosystem is heading — the Functional API, LangGraph Platform,
> LangSmith's feedback loops. I want to be on the team building these tools, not just
> using them."

---

## Part 7: Hiring Manager Questions (2-3 minute answers)

### Q: Walk me through your architecture.

> "It's a 7-node LangGraph graph. Each pipeline stage is its own node:
> orchestrator, signal ingestion, signal qualification, research, solution
> mapping, persona generation, and an HITL gate.
>
> The orchestrator validates input and sets up company states. Then each
> stage node processes ALL companies in parallel using asyncio.gather —
> so if you enter 5 companies, all 5 run at the same time within each stage.
>
> Because each stage is a separate node, LangGraph's astream fires a
> streaming event at every stage boundary. Our frontend picks these up
> via WebSocket and updates the progress bar in real-time.
>
> The state flows through the graph with reducers — rules for merging
> results. Costs get added up across companies, company results get
> merged by ID, and failure lists get concatenated.
>
> At the HITL gate, the graph exits and our REST API takes over. The user
> picks personas, and the API calls synthesis and draft generation directly.
> We handle the human interaction outside the graph because it's a cleaner
> separation — the graph does computation, the API does user interaction."

### Q: What would you improve?

> "Three things, in priority order.
>
> First, I'd add LangSmith production tracing. Right now it's eval-only. Just setting
> two environment variables turns on automatic trace reporting for every LLM call.
> Then I'd add @traceable decorators for a structured trace tree — pipeline, company,
> stage, LLM call. That gives me latency and cost dashboards with zero custom code.
>
> Second, I'd use LangGraph's custom streaming mode to fix the progress bar. Right now
> my company pipeline is one node, so streaming only fires once per company. Custom
> streaming lets me emit events from inside the node at each stage — no need to split
> into separate nodes.
>
> Third, longer term, I'd explore the Functional API for the HITL flow. With @task
> decorators, each stage result is individually checkpointed, so interrupt and resume
> works without the Send serialization issue we hit. I could keep StateGraph for the
> main pipeline and use the Functional API just for the human interaction flow — they
> coexist in the same app."

### Q: How do you handle failures?

> "Every stage has a fallback. The principle is: try the LLM, if it fails, fall back to
> something deterministic, never crash.
>
> Signal scoring normally combines keyword matching with LLM analysis — 40/60 split. If
> the LLM fails, we use keyword-only scoring. It's less nuanced but still works.
>
> Solution mapping normally uses the LLM to identify the core problem. If that fails, we
> return a zero-confidence result. The draft agent sees the low confidence and either
> skips the draft entirely or writes with a cautious tone.
>
> Persona generation normally uses the LLM to customize titles for each company. If that
> fails, we use template personas based on the signal category — still useful, just not
> company-specific.
>
> The user always gets results. The quality varies based on what worked, but the pipeline
> never stops."

---

## Part 8: Technical / Panel Questions

### Q: What LangChain features did you choose NOT to use?

> "A few things, and each was deliberate.
>
> I don't use output parsers — LangChain's JsonOutputParser retries when parsing fails.
> I want the opposite — fall back to deterministic scoring, not retry. My manual JSON
> parsing lets me degrade gracefully.
>
> I don't use LCEL chains. My pipeline runs the same stages in the same order every time.
> Chains are valuable when you need composable, dynamic flows. Mine is fixed.
>
> I don't use LangChain's Tool abstraction for my APIs. JSearch and Tavily need custom
> rate limiting, deduplication, and a cost-tiered escalation system. Wrapping them as
> Tools would hide that control.
>
> The general principle: use the framework where it adds value, go direct where you
> need control."

### Q: Tell me about a limitation you hit with LangGraph.

> "Early on, we used Send() for parallel company dispatch. It worked great
> for parallelism, but broke human-in-the-loop. The checkpointer needs to save
> the graph state when you pause — like a save game. But Send objects are live
> Python objects with function references that can't be converted to storable
> data. It's like trying to bookmark an ongoing phone call — when you reopen
> the book, the call is dead.
>
> We solved it two ways. First, we moved the human interaction outside the
> graph — the graph does computation, the API handles the pause and resume.
> Second, we later refactored away from Send entirely — each pipeline stage
> became its own graph node, and companies run in parallel within each node
> using asyncio.gather. No Send objects means no serialization problem, and
> as a bonus we got real-time streaming for free since astream fires at every
> node boundary.
>
> Looking forward, the Functional API with @task decorators could also solve
> this, since each task's result is individually checkpointed."

### Q: How do you track cost across parallel LLM calls?

> "Every agent function returns two things: updated state and cost incurred. The
> calling function adds up cost and checks budget before each LLM call.
>
> At the graph level, total_cost_usd in AgentState uses an operator.add reducer. So
> when 5 companies run in parallel and each spends $0.08, the merged state correctly
> shows $0.40 — not just the last company's cost.
>
> We also have a budget warning system. At 75% consumption, the backend sends a
> WebSocket event so the frontend can alert the user. And every stage checks remaining
> budget before making an LLM call — if budget is exhausted, it skips the call and
> uses a cheaper fallback instead of crashing.
>
> Default budget is $0.50 per session, configurable in settings."

### Q: Why LangGraph instead of just Python async (asyncio.gather)?

> "Two reasons: typed state management and reducer-based merging.
>
> With asyncio.gather, I'd dispatch 5 coroutines and get 5 results. But then I need
> to manually merge them — add up costs, collect failures, merge per-company states.
> If I add a new field later, I need to update the merge logic.
>
> LangGraph's Annotated reducers declare the merge strategy at the type level. When I
> write total_cost_usd: Annotated[float, operator.add], every parallel branch
> automatically contributes to the sum. No merge code to maintain.
>
> The other reason is observability. LangGraph's astream gives me node-level events.
> With asyncio.gather, I'd need to build my own event system from scratch."

### Q: How would you deploy this on LangGraph Platform?

> "Our langgraph.json is already configured — it points to our build_pipeline function.
> So LangGraph Studio can open it today.
>
> For production deployment, the Platform would replace three things we built ourselves:
> our background asyncio task becomes a platform task queue, our SQLite session store
> becomes Postgres checkpointing, and our custom WebSocket becomes the platform's
> built-in streaming.
>
> The main consideration is our HITL pattern. We'd need to check if the Platform's
> Postgres checkpointer handles Send objects better than the open-source version. If
> it does, we could bring HITL back into the graph. If not, our external HITL pattern
> still works — the API just calls back into the graph after persona selection."

---

## Part 9: Concepts Cheat Sheet

Keep this handy. If you forget a term during the interview, use the plain English version.

| Term | Plain English | In SignalForge |
|------|-------------|---------------|
| **Node** | A box that does work | Each pipeline stage (signal ingestion, research, etc.) |
| **Edge** | An arrow connecting boxes | "After orchestrator, go to company_pipeline" |
| **State** | The shared data clipboard | Company results, costs, status flags |
| **Reducer** | Rule for combining parallel results | "Add up costs from all companies" |
| **Send()** | "Run this work package in parallel" | We used this originally, then moved to asyncio.gather inside separate nodes |
| **Checkpointer** | Save point system | We use our own SQLite instead |
| **interrupt()** | Pause and wait for a human | We couldn't use it (Send serialization issue) |
| **@entrypoint** | "This is the main function" (Functional API) | Not used yet, could help with HITL |
| **@task** | "This is a unit of work" (Functional API) | Not used yet, each stage could be a task |
| **Command** | "Resume from pause with this data" (Functional API) | Not used yet |
| **astream()** | Watch the graph execute in real-time | We use it but only get one event per company |
| **stream_mode="custom"** | Emit your own events during execution | Would fix our progress bar |
| **@traceable** | "Log this function to LangSmith" | Not added yet, planned |
| **LangSmith** | Dashboard for monitoring AI apps | We use it for eval only |
| **LangGraph Platform** | Managed hosting for LangGraph apps | Not deployed yet, config is ready |

---

## Part 10: Your Roadmap (Shows Vision)

When asked "what would you build next?" — these show you think beyond just coding.

**1. LangSmith Observability (Issues #31-32)**
> "Turn on production tracing and add @traceable to each agent. This gives per-stage
> latency and cost dashboards with almost no code changes."

**2. LangSmith Feedback Flywheel (Issues #33-34)**
> "When users approve or reject drafts, log it as feedback. Approved drafts become
> test datasets. Now we have: approve → dataset → eval → improve → better drafts."

**3. Custom Streaming for Progress (Issue #29)**
> "Use stream_mode='custom' so each stage can emit progress events from inside the
> node. Fixes the progress bar without splitting into separate nodes."

**4. Capability + Intelligence Integration (Issue #30)**
> "Our signal detection system and our seller knowledge are disconnected. Connecting
> them means when a signal matches a capability, we already know the seller's angle,
> proof points, and sales play for that exact problem."

**5. Functional API for HITL (future)**
> "Explore @entrypoint and @task for the human-in-the-loop flow. Task-level
> checkpointing might solve the Send serialization issue and bring HITL back into
> the graph where it belongs."

---

## Part 11: Things You Should Be Ready to Draw on a Whiteboard

1. **The pipeline flow** — 7 boxes in a line with the HITL gate at the end
2. **The graph evolution** — started with 3 nodes + Send(), refactored to 7 nodes + asyncio.gather()
3. **Parallel within nodes** — each node runs all companies via gather(), reducers merge results
4. **The HITL pattern** — graph exits at hitl_gate → API pauses → user picks → API calls synthesis directly
5. **The LangSmith flywheel** — tracing → feedback → datasets → eval → prompt improvement

---

## Part 12: Where Everything Lives in the Code

Use this when you want to look at the actual code for any concept.

### LangGraph Pipeline

| What | File | What to Look At |
|------|------|----------------|
| Graph assembly (3 nodes, edges) | `backend/pipeline.py` lines 228-244 | `StateGraph`, `add_node`, `add_edge` |
| Per-company pipeline (all 8 stages) | `backend/pipeline.py` lines 47-205 | The monolithic function |
| Parallel dispatch (Send) | `backend/agents/orchestrator.py` lines 161-187 | `dispatch_companies()` returns `list[Send]` |
| State with reducers | `backend/models/state.py` lines 203-228 | `AgentState` with `Annotated` types |
| LangGraph Studio config | `langgraph.json` | Entry point for Studio |

### Pipeline Stages (Each Agent)

| Stage | File | Main Function |
|-------|------|---------------|
| Signal Ingestion | `backend/agents/signal_ingestion.py` | `run_signal_ingestion()` |
| Signal Qualification | `backend/agents/signal_qualification.py` | `run_signal_qualification()` |
| Research | `backend/agents/research.py` | `run_research()` |
| Solution Mapping | `backend/agents/solution_mapping.py` | `run_solution_mapping()` |
| Persona Generation | `backend/agents/persona_generation.py` | `run_persona_generation()` |
| HITL Gate | `backend/agents/hitl_gate.py` | `run_persona_selection_gate()` |
| Synthesis | `backend/agents/synthesis.py` | `run_synthesis()` |
| Draft Generation | `backend/agents/draft.py` | `run_drafts_for_company()` |

### HITL (Human-in-the-Loop)

| What | File | What to Look At |
|------|------|----------------|
| Gate that pauses pipeline | `backend/agents/hitl_gate.py` lines 28-41 | Sets status to AWAITING_HUMAN |
| Apply user's selection | `backend/agents/hitl_gate.py` lines 44-62 | Validates and applies persona IDs |
| Resume outside graph | `backend/api/routes/personas.py` lines 104-267 | Calls synthesis + drafts directly |
| LangGraph node (signaling) | `backend/agents/hitl_gate.py` lines 65-87 | Returns awaiting flag |

### LLM Usage

| What | File | Pattern |
|------|------|---------|
| Standard LLM call | Every agent | `await llm.ainvoke([HumanMessage(content=prompt)])` |
| Streaming LLM call | `backend/agents/chat_assistant.py` line 133 | `async for chunk in llm.astream(messages)` |
| Provider routing | Every agent | `_make_llm()` → ChatAnthropic or ChatOpenAI |
| Token tracking | Every agent | `response.usage_metadata` for token counts |

### WebSocket & Streaming

| What | File | What to Look At |
|------|------|----------------|
| Event broadcaster | `backend/api/websocket.py` | `ConnectionManager` class |
| Pipeline streaming | `backend/api/routes/sessions.py` line 117 | `graph.astream()` loop |
| Frontend WebSocket | `frontend/src/App.tsx` lines 179-210 | `connectWebSocket()` + event handler |
| Frontend reconnection | `frontend/src/api/client.ts` lines 190-270 | `WsManager` with backoff |
| Progress bar | `frontend/src/components/ProgressBar.tsx` | Stage matching |

### LangSmith

| What | File | What to Look At |
|------|------|----------------|
| LLM-as-judge eval | `tests/eval/draft_eval.py` | Rubric + scoring |
| Config/settings | `backend/config/loader.py` | API key storage |

### Other Key Files

| What | File |
|------|------|
| Capability map (signal matching) | `backend/config/capability_map.py` |
| Seller intelligence (web scraping) | `backend/agents/seller_intelligence.py` |
| Config loader (all settings) | `backend/config/loader.py` |
| Frontend main app | `frontend/src/App.tsx` |
| Setup wizard | `frontend/src/components/SetupWizard.tsx` |

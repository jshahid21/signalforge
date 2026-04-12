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

## Part 2: LangGraph Concepts — From Zero

### What is a "graph"?

A graph is just **boxes connected by arrows**. Each box does something. The arrows say "go here next."

In SignalForge, our graph looks like this:

```
[Orchestrator] → [Company Pipeline] → [HITL Gate] → [Done]
```

That's 3 boxes (called **nodes**) connected by arrows (called **edges**).

**Where in the code:** `backend/pipeline.py` lines 228-244

```python
graph = StateGraph(AgentState)                          # Create the graph
graph.add_node("orchestrator", orchestrator_node)       # Add box 1
graph.add_node("company_pipeline", company_pipeline)    # Add box 2
graph.add_node("hitl_gate", hitl_gate_node)             # Add box 3
graph.add_edge("company_pipeline", "hitl_gate")         # Arrow: box 2 → box 3
graph.add_edge("hitl_gate", END)                        # Arrow: box 3 → done
graph.set_entry_point("orchestrator")                   # Start at box 1
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

### What is `Send()`?

This is how LangGraph does **parallel processing**. Instead of going to one next node, you can send **multiple copies** of work to the same node.

In SignalForge: if you enter 5 company names, the orchestrator creates 5 `Send()` objects — one per company. LangGraph runs all 5 in parallel.

**Where in the code:** `backend/agents/orchestrator.py` lines 161-187

```python
def dispatch_companies(state):
    sends = []
    for company_id, company_state in state["company_states"].items():
        sends.append(Send("company_pipeline", {
            "company_state": company_state,
            # ... other data this company needs
        }))
    return sends  # LangGraph runs all of these at the same time
```

**Plain English:** "For each company, send a work package to the company_pipeline node. Run them all at once."

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

### Story 1: "Why we run companies in parallel with Send()"

**The situation:** A user enters 5 company names. Processing each takes 30-60 seconds (multiple LLM calls, API searches). Running them one by one = 3-5 minutes of waiting.

**What we did:** Used LangGraph's `Send()` to dispatch all 5 simultaneously. Each company gets its own isolated work package.

**The challenge:** When 5 branches run in parallel and all finish at different times, how do you combine their results? Company A's cost was $0.08, Company B's was $0.12 — the total needs to be $0.20, not just the last one to finish.

**How we solved it:** Annotated reducers on the state. `total_cost_usd: Annotated[float, operator.add]` tells LangGraph "add these up." `company_states: Annotated[dict, merge_dict]` tells it "merge the dictionaries so each company keeps its own results."

**Look at:** `backend/agents/orchestrator.py` (the Send dispatch) and `backend/models/state.py` (the reducers)

---

### Story 2: "Why our human-in-the-loop gate lives outside the graph"

**The situation:** After generating personas, we want the user to review and select which ones to target before generating emails. The pipeline needs to **pause** and **wait** for human input.

**What LangGraph offers:** `interrupt()` — it pauses the graph and saves state via a checkpointer. When the user responds, you resume from where you left off.

**What went wrong:** When you resume, LangGraph tries to re-run the orchestrator's dispatch function, which produces `Send()` objects. But the checkpointer (the save system) **can't save `Send()` objects** — it doesn't know how to convert them to data it can store. So the resume crashes.

**What we did instead:** We let the graph run all the way through and exit. When it exits, a flag says "these companies need persona selection." Our REST API handles the pause — the frontend shows the persona picker, the user selects, and the API calls synthesis and draft generation directly. No graph re-entry.

**Why this is actually better:** The graph does computation. The API does user interaction. Clean separation. But it IS a LangGraph limitation.

**How the Functional API could help:** With `@task` decorators, each stage's result is individually checkpointed. So `interrupt()` wouldn't need to re-serialize Send objects — it would just pick up from the last completed task. This is the newer approach that could bring HITL back into the graph.

**You can use both APIs together.** We could keep our StateGraph for the main pipeline and add a Functional API `@entrypoint` specifically for the HITL → synthesis → draft flow. They coexist in the same app.

**Look at:** `backend/agents/hitl_gate.py` (the gate) and `backend/api/routes/personas.py` (the resume outside the graph)

---

### Story 3: "Why the progress bar was stuck and what streaming modes would fix it"

**The situation:** Each company has a 5-stage progress bar (Signals → Qualifying → Researching → Mapping → Generating). But it never moved — it stayed on the first stage until everything finished, then jumped to done.

**Root cause:** Our `company_pipeline` function runs all 8 stages inside **one LangGraph node**. LangGraph's streaming (`astream()`) only fires events at **node boundaries** — when one node finishes and the next starts. Since the whole company flow is one node, there's only one event: "company finished."

**What we did (bugfix):** Each stage now sets `current_stage` at the start of its function. The session endpoint's `astream` loop picks this up at the node boundary and broadcasts it via WebSocket. The progress bar shows the final state correctly, but doesn't animate in real-time during execution.

**What would really fix it:** LangGraph's `custom` streaming mode. Inside a node, you can call `emit()` to send data to whoever is streaming. Each stage could emit a progress event:

```python
async def company_pipeline(input, config):
    # Stage 1
    cs = await run_signal_ingestion(cs, ...)
    emit({"stage": "signal_ingestion", "status": "done"})  # Real-time event!
    
    # Stage 2
    cs = await run_signal_qualification(cs, ...)
    emit({"stage": "signal_qualification", "status": "done"})
    ...
```

No need to split into separate nodes. The `custom` stream mode lets you emit events from inside a node.

**Alternative:** The `tasks` streaming mode (with Functional API's `@task`) would automatically emit start/finish events for each task — no manual `emit()` needed.

**Look at:** `backend/pipeline.py` (the monolithic company_pipeline) and `frontend/src/components/ProgressBar.tsx`

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

> "At a high level, it's a 3-node LangGraph graph.
>
> Node 1, the orchestrator, takes company names and dispatches them in parallel using
> Send — if you enter 5 companies, 5 copies of the pipeline run at the same time.
>
> Node 2, company_pipeline, is where the real work happens. For each company, it runs
> signal discovery, scoring, research, solution mapping, and persona generation. All
> sequentially within one node.
>
> Node 3, hitl_gate, checks if any company needs human persona selection. If so, the
> graph exits and our REST API takes over for the human interaction part.
>
> The state flowing through the graph has reducers — rules for combining results from
> parallel branches. Costs get added up, company results get merged by ID, and lists
> get concatenated.
>
> After the human picks personas, the API calls synthesis and draft generation directly,
> outside the graph. This was a deliberate choice because of a checkpointer limitation
> with Send objects."

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

> "The checkpointer can't serialize Send objects.
>
> My pipeline uses Send for parallel company processing. When I tried to add a
> human-in-the-loop pause using interrupt(), the checkpointer needed to save the
> graph state. But the state included Send objects from the dispatch function, and
> it couldn't convert them to storable data.
>
> I solved it by moving the human interaction outside the graph entirely. The graph
> runs computation, the REST API handles user interaction, and they communicate
> through shared state in our database.
>
> If I were redesigning today, I'd look at the Functional API where each @task is
> individually checkpointed. That might avoid the Send serialization issue since
> tasks persist their own results."

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
| **Send()** | "Run this work package in parallel" | One per company, all run simultaneously |
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

1. **The pipeline flow** — 8 boxes in a line with the HITL pause in the middle
2. **The graph** — 3 nodes (orchestrator → company_pipeline → hitl_gate) with the Send fan-out
3. **Parallel + reducers** — 5 branches merging costs and results
4. **The HITL workaround** — graph exits → API pauses → user picks → API calls synthesis directly
5. **The LangSmith flywheel** — tracing → feedback → datasets → eval → prompt improvement

# Interview Talking Points — Deployed Engineer (Dallas)

> Gap analysis between your resume and the job requirements.
> Use these as talking points, not scripts. Know the bullet, tell the story.

---

## Resume Changes to Make

### 1. Move AI Projects to the Top
Your SignalForge and Omni-Help projects are more relevant to this role than
Oracle job history. Put "Selected AI Projects" right after Professional Summary.

### 2. Update SignalForge Description
Current: "Designing a stateful multi-agent system... (In Progress)"

Replace with:
> **SignalForge — Proactive Sales Signal Intelligence Engine (LangGraph, FastAPI, React)**
> Built a production-ready pipeline that discovers buying signals, qualifies them
> with hybrid LLM+keyword scoring, generates buyer personas, and writes
> persona-targeted outreach emails. Features parallel company processing via
> LangGraph Send(), human-in-the-loop persona selection, LangSmith
> tracing/feedback/eval integration, and graceful degradation at every stage.
> Full-stack: React/TypeScript frontend with WebSocket real-time updates, FastAPI
> backend, 400+ tests.

### 3. Add JavaScript/TypeScript to Skills
The job requires "Strong Python and JavaScript fundamentals." You built the
React/TypeScript frontend. Add to skills line:
> React, TypeScript, Vite (frontend)

### 4. Change "Designed" to "Built" and "Deployed"
The role is "Deployed Engineer" — they want doers, not architects.
- "Designed and prototyped" → "Built and deployed"
- "Designing a stateful multi-agent system" → "Built a stateful multi-agent system"
- "Implementing human-in-the-loop" → "Shipped human-in-the-loop"

### 5. Add Outcome Numbers Where Possible
- Omni-Help: "Reduced manual lookup time by routing queries to the correct system"
  → add a number if you have one: "Reduced manual lookup time by ~70%"
- SignalForge: "11 PRs merged, 400+ tests, end-to-end pipeline processing 5 companies in parallel"

---

## Gap: "Strong Python fundamentals"

**What they'll ask:** Not algorithm puzzles. More like: "Walk me through this
code. What does async/await do here? Why is this a TypedDict vs Pydantic model?
How does this error handling work?"

**Your prep:** Read `docs/python-fundamentals-walkthrough.md` in this project.
It walks through every Python concept in SignalForge line by line.

**How to talk about it:**
> "My Python started with ML engineering — NumPy, Pandas, Scikit-learn, basic
> scripting. Through building SignalForge, I went deep on async programming,
> Pydantic data validation, TypedDict state management, and production patterns
> like graceful fallbacks and decorator-based tracing."

---

## Gap: "JavaScript fundamentals"

**What they'll ask:** Probably not deep JS questions, but they want to know
you're comfortable on both sides.

**Your talking point:**
> "The SignalForge frontend is React with TypeScript. I built the WebSocket
> manager with exponential backoff reconnection, the Zustand state store, and
> components like the persona table with inline editing and the draft panel with
> email composer UX. I'm comfortable reading and writing TypeScript — my
> strength is on the Python backend side, but I can work across the stack."

---

## Gap: "Takes responsibility for outcomes, not just recommendations"

**What they're looking for:** You don't just advise — you own the result.

**Stories to tell:**

1. **SignalForge end-to-end:** "I didn't just design the architecture — I built
   the entire app, wrote the tests, found bugs by running it myself, filed
   issues, and shipped fixes. When the progress bar wasn't working, I traced
   it to a mismatch between backend stage names and frontend expectations, filed
   the issue, and had it fixed in the same session."

2. **Oracle $1M ARR accounts:** "I didn't just propose solutions — I built the
   POCs, ran the demos, and stayed through deployment. The $1M+ ARR didn't come
   from a slide deck, it came from proving the solution worked in their environment."

3. **HITL bug discovery:** "I was testing the app as a user, not just reviewing
   code. I found that persona confirmation was confusing because the UI didn't
   show which companies still needed confirmation. I diagnosed it, created the
   issue with root cause analysis, and the fix was merged within the hour."

---

## Gap: "Post-sale advisory"

**What they're looking for:** Can you help customers after they buy, not just
during the sale?

**Your talking point:**
> "At Oracle, the engagement didn't end at the sale. I led ongoing architecture
> reviews, helped customers optimize their deployments, and ran enablement
> sessions for their teams. When issues came up post-deployment, I was the
> technical escalation point. That's similar to what Deployed Engineers do —
> you're embedded with the customer through the whole lifecycle."

---

## Strength: Customer-Facing Technical Work

This is your biggest advantage. Most engineers applying for this role are
backend developers who've never sat across from a customer.

**Your talking points:**

> "At Oracle, I ran architecture sessions where I'd whiteboard a customer's
> entire system, identify where cloud or AI could help, and design the solution
> live. That's exactly what a POC or evaluation looks like — you're figuring it
> out together, not presenting a pre-built answer."

> "I've done this with enterprise accounts — people who ask hard questions and
> push back on tradeoffs. I'm comfortable saying 'I don't know, let me dig in'
> and coming back with a real answer."

---

## Strength: LangChain/LangGraph Production Experience

Most candidates have built tutorials. You have a real app with real problems.

**Your talking points:**

> "I hit the Send() serialization issue with checkpointers — Send objects can't
> be saved to disk because they contain live Python function references. That's
> not in any tutorial. I first worked around it by moving HITL outside the graph,
> then later refactored away from Send entirely — each stage became its own node
> with asyncio.gather for parallelism. That's the kind of problem Deployed
> Engineers help customers solve."

> "I built the full LangSmith integration — not just tracing, but structured
> traces with @traceable, feedback logging on draft approve/reject, and
> evaluation datasets from approved drafts. That's the complete observability
> story."

> "I use LangGraph for what it's good at — parallel dispatch with safe state
> merging — and go direct for what needs control — custom JSON parsing with
> graceful fallback instead of output parsers. I know when to use the framework
> and when not to."

---

## Strength: You Know the Product From a Customer's Perspective

You've BEEN the customer. You can empathize with the people you'd be helping.

**Your talking point:**

> "I've experienced LangChain's products as a builder. I know what's great —
> Send() with reducers saved me from writing my own parallel merge logic. And
> I know what's painful — the checkpointer can't serialize Send objects, so
> HITL with parallel dispatch requires a workaround. That customer empathy is
> what makes a Deployed Engineer effective. You're not reading from docs — you've
> felt the pain yourself."

---

## The Question You'll Definitely Get: "Why LangChain?"

> "Two reasons. First, I've been building with the ecosystem and I've seen both
> what works and what's hard. The products are solving real problems — LangGraph
> gave me parallel execution with typed state merging, LangSmith gave me
> production observability with almost no code changes. I want to be on the team
> making these tools better, not just consuming them.
>
> Second, the Deployed Engineer role is exactly the intersection of what I do —
> I build production AI systems AND I work directly with customers on technical
> problems. At Oracle I was the person in the room whiteboarding architecture
> and building the POC. At LangChain I'd be doing the same thing, but with
> tools I'm deeply familiar with and a product I believe in."

---

## The Question You'll Definitely Get: "Tell me about a technical challenge"

Use the HITL story. It has everything: a real problem, investigation, a
framework limitation, a creative workaround, and a path forward.

> "My pipeline originally used LangGraph's Send to process multiple companies
> in parallel. After generating personas, I needed to pause for human review.
>
> LangGraph has interrupt() for this — it saves the graph state and resumes
> later. But the save system — the checkpointer — needs to convert everything
> to storable data, like JSON. Send objects are live Python objects with
> function references — they can't be converted. Think of it like trying to
> save an ongoing phone call to a file. The resume would crash.
>
> I solved it in two steps. First, I moved the human interaction outside the
> graph — the graph runs to completion, exits with a flag, and the REST API
> handles the pause and resume. Second, I later refactored the entire graph
> — instead of one big node with Send, each stage became its own node. Companies
> run in parallel inside each node using asyncio.gather. No more Send objects
> means no serialization problem, and as a bonus I got real-time streaming
> because astream fires at every node boundary.
>
> The evolution was: Send for parallelism → hit checkpointer limitation →
> HITL workaround → full refactor to separate nodes. Each step taught me
> something deeper about how LangGraph works internally."

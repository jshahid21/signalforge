# Python Fundamentals — Reading SignalForge Code

> This doc walks through real SignalForge code line by line.
> The goal is to make you comfortable reading and explaining any file in the project.
> Read this top to bottom — each section builds on the previous one.

---

## 1. Functions — The Building Blocks

A function is a named block of code you can call. Let's look at a simple one
from our web crawler:

```python
def _validate_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("URL must use HTTPS")
    return url.strip()
```

Reading this line by line:

- `def _validate_url(url: str) -> str:` — "I'm creating a function called
  `_validate_url`. It takes one input called `url` which should be a string
  (`str`). It gives back a string (`-> str`)."
  - The `_` at the start is a naming convention meaning "this is internal,
    not meant to be called from outside this file."
  - `: str` and `-> str` are **type hints** — they don't enforce anything,
    they're labels that help you (and your editor) know what to expect.

- `parsed = urlparse(url.strip())` — "Call `url.strip()` (removes whitespace
  from both ends of the string), then pass that to `urlparse()` (breaks a URL
  into parts like scheme, domain, path). Store the result in a variable called
  `parsed`."

- `if parsed.scheme != "https":` — "If the URL doesn't start with https..."

- `raise ValueError("URL must use HTTPS")` — "...stop everything and report
  an error. `raise` is like throwing an alarm — whatever called this function
  will get this error unless it catches it."

- `return url.strip()` — "If we got past the check, give back the cleaned URL."

**Key concept:** Functions take inputs (called **parameters** or **arguments**),
do work, and give back a result (via `return`). If something goes wrong, they
can `raise` an error.

---

## 2. Dictionaries — How We Store Company Data

A dictionary (`dict`) stores key-value pairs. It's like a labeled filing cabinet.

In SignalForge, every company's data is stored as a dictionary:

```python
company_state = {
    "company_id": "stripe",
    "company_name": "Stripe",
    "status": "running",
    "current_stage": "signal_ingestion",
    "total_cost_usd": 0.0,
}
```

Reading and writing values:

```python
# Reading — use the key to get the value
name = company_state["company_name"]        # "Stripe"
cost = company_state.get("total_cost_usd", 0.0)  # 0.0

# Writing — assign to a key
company_state["status"] = "completed"
company_state["current_stage"] = "done"
```

- `["company_name"]` — get the value. Crashes if the key doesn't exist.
- `.get("total_cost_usd", 0.0)` — get the value, but if the key doesn't
  exist, return `0.0` instead of crashing. The second argument is the default.

**Why this matters:** LangGraph state is a dictionary. Every node reads from
it and writes to it. When you see `cs["current_stage"] = "research"`, that's
updating the shared state.

---

## 3. TypedDict — A Dictionary With a Blueprint

A regular dict can have any keys. A TypedDict says "this dictionary MUST have
these specific keys with these specific types."

```python
class CompanyState(TypedDict):
    company_id: str
    company_name: str
    status: PipelineStatus
    current_stage: str
    generated_personas: list[Persona]
    total_cost_usd: float
```

This doesn't create a company — it creates a **blueprint**. It says:
- Every CompanyState dictionary must have a `company_id` that's a string
- It must have a `status` that's a PipelineStatus (an enum — a fixed set of choices)
- It must have `generated_personas` that's a list of Persona objects
- etc.

**Why LangGraph uses TypedDict instead of regular dict:** It needs to know the
shape of the state upfront so it can apply reducers (merge rules) to the right
fields.

---

## 4. Lists and Loops

A list is an ordered collection. Loops go through each item one at a time.

```python
# A list of company names
companies = ["Stripe", "Datadog", "HashiCorp"]

# Loop through each one
for company in companies:
    print(company)
# Prints: Stripe, then Datadog, then HashiCorp
```

**List comprehension** — a one-line way to build a new list from an existing one:

```python
# Long way
keywords = []
for entry in capability_map.entries:
    for kw in entry.problem_signals:
        keywords.append(kw)

# Short way (list comprehension) — does the same thing
keywords = [kw for entry in capability_map.entries for kw in entry.problem_signals]
```

Reading the comprehension: "For each `entry` in `capability_map.entries`, for
each `kw` in that entry's `problem_signals`, add `kw` to the list."

**Filtering with comprehension:**

```python
# Only keep companies that failed
failed = [cid for cid, cs in states.items() if cs.get("status") == "failed"]
```

Reading this: "For each `cid` (company ID) and `cs` (company state) in the
states dictionary, if the status is 'failed', add the company ID to the list."

---

## 5. If/Else — Decision Making

```python
if confidence >= 60:
    tone = "full_pitch"
elif confidence >= 35:
    tone = "hedged"
else:
    tone = "skip"
```

Nothing surprising here. `elif` means "else if" — checked only when the
previous condition was False.

**Truthiness shortcuts you'll see in the code:**

```python
# These are "falsy" in Python (treated as False):
#   None, 0, "", [], {}, False

# So this:
if not llm_model:
    use_fallback()

# Means: "if llm_model is empty string, None, or missing — use fallback"

# And this:
signals = cs.get("raw_signals") or []

# Means: "get raw_signals from cs. If it's None or empty, use [] instead"
```

---

## 6. Try/Except — When Things Go Wrong

`try` means "attempt this code." `except` means "if it crashes, do this instead."

This is the core of our graceful fallback pattern:

```python
try:
    # Try the LLM call
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    parsed = json.loads(response.content)
    cost = 0.004
except Exception:
    # LLM failed — use a safe fallback instead of crashing
    parsed = None
    cost = 0.0

if parsed is None:
    # Use deterministic scoring (no LLM needed)
    result = fallback_result
else:
    result = parsed
```

Line by line:
- `try:` — "try running this block of code"
- If `llm.ainvoke()` crashes (network error, timeout, bad response), Python
  jumps to the `except` block
- `except Exception:` — "catch any error" (Exception is the parent of all errors)
- We set `parsed = None` to signal "LLM didn't work"
- Later, we check `if parsed is None` and use a fallback

**Why this matters for the interview:** "Every stage has graceful fallback.
Try the LLM, catch any failure, fall back to deterministic — never crash."

---

## 7. async/await — Doing Multiple Things at Once

This is the most important concept for SignalForge. Here's why we need it:

**The problem:** Our pipeline calls an LLM, which takes 2-3 seconds. While
waiting for Stripe's LLM response, we could be processing Datadog. But normal
Python just... waits.

**The solution:** `async` and `await` let Python do other work while waiting.

```python
# Regular function — blocks everything while waiting
def get_signals(company):
    response = llm.invoke(prompt)     # nothing else can happen for 3 seconds
    return response

# Async function — lets other work happen while waiting
async def get_signals(company):
    response = await llm.ainvoke(prompt)  # Python can do other things for 3 seconds
    return response
```

The key words:
- `async def` — "this function might need to wait for things"
- `await` — "wait for this to finish, but let other async functions run while waiting"

**It's like a restaurant:** The waiter (Python) takes your order, sends it to
the kitchen (LLM), and instead of standing at your table waiting, goes to take
another table's order. When the kitchen rings the bell, the waiter comes back
with your food.

**Where you see this in SignalForge:**

```python
# backend/pipeline.py — the company pipeline
async def company_pipeline(input):
    # Each await lets other companies run while this one waits
    cs, cost1 = await run_signal_ingestion(cs, ...)    # wait for API
    cs, cost2 = await run_signal_qualification(cs, ...) # wait for LLM
    cs, cost3 = await run_research(cs, ...)             # wait for LLM
    ...
```

Five companies call this function at the same time (via Send). While company A
is `await`ing its LLM response, company B's code runs. That's why 5 companies
don't take 5x the time.

**Running things in background:**

```python
# backend/api/routes/sessions.py
task = asyncio.create_task(_run_pipeline_task())
# This starts the pipeline running in the background
# The API can immediately respond to the user: "session started"
```

`create_task()` says "start running this, but don't wait for it to finish —
continue with the next line of code."

---

## 8. Tuples — Functions That Return Multiple Things

Every agent returns TWO things: the updated state AND how much it cost.

```python
async def run_research(cs, ...) -> tuple[CompanyState, float]:
    # ... do research ...
    return cs, cost_incurred
```

- `tuple[CompanyState, float]` — "returns two things: a CompanyState and a number"
- `return cs, cost_incurred` — pack two values together

The caller unpacks them:

```python
cs, research_cost = await run_research(cs, ...)
total_cost += research_cost
```

- `cs, research_cost = ...` — "the first value goes into `cs`, the second into
  `research_cost`"

This is why every stage in `backend/pipeline.py` looks like:
```python
cs, cost1 = await run_signal_ingestion(cs, ...)
total_cost += cost1
cs, cost2 = await run_signal_qualification(cs, ...)
total_cost += cost2
```

Each stage updates `cs` (the company state) and reports its cost.

---

## 9. Classes — Blueprints for Objects

A class groups data and functions together. We use them for configuration:

```python
class ConnectionManager:
    def __init__(self):
        self._connections = {}    # session_id → set of WebSocket connections

    async def connect(self, websocket, session_id):
        await websocket.accept()
        self._connections.setdefault(session_id, set()).add(websocket)

    async def broadcast(self, session_id, event):
        for ws in self._connections.get(session_id, set()):
            await ws.send_text(json.dumps(event))
```

- `class ConnectionManager:` — "I'm defining a blueprint called ConnectionManager"
- `def __init__(self):` — "when someone creates a new ConnectionManager, run
  this setup code." `self` refers to the object being created.
- `self._connections = {}` — "this object has a property called `_connections`,
  starting as an empty dictionary"
- `async def connect(self, websocket, session_id):` — "this object has a
  method (function) called `connect`." `self` is always the first parameter —
  it's how the method accesses the object's data.

**Using it:**

```python
manager = ConnectionManager()              # creates one, runs __init__
await manager.connect(websocket, "abc123") # calls the connect method
await manager.broadcast("abc123", event)   # calls broadcast
```

---

## 10. Decorators — Wrapping Functions

A decorator adds behavior to a function without changing the function itself.

```python
@traceable(name="run_research")
async def run_research(cs, ...):
    ...
```

**What this actually does:** Before `run_research` runs, the `@traceable`
wrapper:
1. Records the start time
2. Calls the real `run_research`
3. Records the end time
4. Sends the timing data to LangSmith

The function itself doesn't know it's being traced. The decorator handles it.

**Think of it like a security badge scanner at a door.** The scanner (decorator)
logs who entered and when, but the room (function) doesn't change. You walk in
the same way whether the scanner is there or not.

**Our no-op decorator** (`backend/tracing.py`):

```python
try:
    from langsmith import traceable
except ImportError:
    def traceable(func=None, *, name="", **kwargs):
        if func is None:
            return lambda f: f    # return the function unchanged
        return func               # return the function unchanged
```

This says: "Try to import the real `traceable` from langsmith. If langsmith
isn't installed, create a fake one that does nothing — just returns the
function as-is." This way agents work whether or not langsmith is installed.

---

## 11. Imports — Getting Code From Other Files

```python
# Import a specific thing from a file
from backend.agents.hitl_gate import apply_persona_selection

# Import a whole module
import json

# Import with a fallback (try/except)
try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None
```

The try/except import pattern is everywhere in SignalForge. It means: "If this
library is installed, use it. If not, set it to `None` and we'll handle it
later." This keeps the app from crashing if an optional dependency is missing.

```python
# Later in the code:
if ChatAnthropic is None:
    raise RuntimeError("langchain-anthropic not installed")
```

---

## 12. Pydantic — Data Validation

Pydantic models are like TypedDict but with superpowers: they validate data,
convert types, and have defaults.

```python
from pydantic import BaseModel, Field

class SellerProfileConfig(BaseModel):
    company_name: str = ""                              # default: empty string
    portfolio_items: list[str] = Field(default_factory=list)  # default: empty list
    website_url: Optional[str] = None                   # default: None (no value)
```

- `BaseModel` — "this is a Pydantic model" (like inheriting a template)
- `str = ""` — "if not provided, default to empty string"
- `Field(default_factory=list)` — "if not provided, create a new empty list"
  (we use `default_factory` instead of `= []` because Python shares mutable
  defaults between instances, which causes bugs)
- `Optional[str] = None` — "this can be a string OR None"

**Creating and using:**

```python
# Pydantic validates the data when you create it
profile = SellerProfileConfig(company_name="Acme Corp")
print(profile.company_name)    # "Acme Corp"
print(profile.website_url)     # None (used the default)

# Convert to dictionary
data = profile.model_dump()    # {"company_name": "Acme Corp", ...}

# Convert to/from JSON
json_str = profile.model_dump_json()
profile2 = SellerProfileConfig.model_validate_json(json_str)
```

**TypedDict vs Pydantic in SignalForge:**
- TypedDict → LangGraph state (lightweight, no validation overhead)
- Pydantic → API request/response bodies, config files (need validation)

---

## 13. Putting It All Together — Reading a Full Agent

Here's a simplified version of how a pipeline stage works. Read it top to
bottom — you now know every concept used here.

```python
# Imports
from backend.tracing import traceable                    # our decorator
from backend.models.state import CompanyState            # TypedDict blueprint

_LLM_COST = 0.004  # constant — how much one LLM call costs

# The main function — async because it calls an LLM
@traceable(name="run_solution_mapping")                  # decorator: log to LangSmith
async def run_solution_mapping(
    cs: CompanyState,                                    # input: company data (dict)
    llm_provider: str,                                   # "anthropic" or "openai"
    llm_model: str,                                      # "claude-sonnet-4-6"
    current_total_cost: float,                           # how much spent so far
    max_budget_usd: float,                               # spending limit
) -> tuple[CompanyState, float]:                         # returns: updated state + cost

    # Set the current stage (for progress bar)
    cs = dict(cs)                                        # make a copy (don't modify original)
    cs["current_stage"] = "solution_mapping"

    # Check budget before spending money
    if current_total_cost >= max_budget_usd:
        cs["solution_mapping"] = fallback_mapping        # use free fallback
        return cs, 0.0                                   # return with zero cost

    # Try the LLM call
    try:
        llm = ChatAnthropic(model=llm_model)             # create LLM client
        prompt = f"Analyze {cs['company_name']}..."       # build the prompt
        response = await llm.ainvoke(                     # call LLM (async — other work can happen)
            [HumanMessage(content=prompt)]
        )
        parsed = json.loads(response.content)             # parse JSON from response
        cost = _LLM_COST
    except Exception:                                     # LLM failed
        parsed = None
        cost = 0.0

    # Use result or fallback
    if parsed:
        cs["solution_mapping"] = parsed                   # store LLM result
    else:
        cs["solution_mapping"] = fallback_mapping         # store safe fallback

    return cs, cost                                       # return updated state + cost spent
```

**This is the pattern for every agent in SignalForge.** They all:
1. Set `current_stage` (for the progress bar)
2. Check budget
3. Try an LLM call
4. Fall back if it fails
5. Return `(updated_state, cost)`

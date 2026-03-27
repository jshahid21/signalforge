# Lessons Learned

> Extracted from `codev/reviews/`. Last updated: 2026-03-27

## Testing

**Patch at point of use, not definition** (Spec 1)
When a module uses `from X import Y`, the name `Y` is bound in the module's own namespace.
Patching `X.Y` has no effect on already-imported modules. Always patch `using_module.Y`.
Example: `backend.pipeline` does `from backend.agents.draft import run_drafts_for_company`,
so the correct patch target is `backend.pipeline.run_drafts_for_company`.

**E2E tests for qualified fixtures must forbid SKIPPED/FAILED** (Spec 1)
If a test fixture is defined as expected-to-qualify (e.g., LangChain), the E2E test assertion
must explicitly exclude `PipelineStatus.SKIPPED` and `PipelineStatus.FAILED`. Allowing these
statuses turns the test into a "didn't crash" check rather than a functional verification.

**Agent-level mocking via function patches is more resilient than LLM constructor patches** (Spec 1)
Patching the calling function (e.g., `call_llm_severity`) is more stable than patching
`ChatAnthropic` directly, since agents may initialize LLM instances in different ways.
Use function-level patches when the agent's LLM initialization path is opaque.

**LLM eval harness should be separate from pytest** (Spec 1)
Tests requiring real LLM API keys slow CI and can flake on rate limits. Keep LLM-as-judge
evaluation in a separate script (e.g., `tests/eval/draft_eval.py`) excluded from pytest discovery.

## Architecture

**LangGraph `Command(goto=...)` not `Command(send=...)` in v1.1+** (Spec 1)
LangGraph 1.1.x renamed the `send` parameter to `goto` in `Command`. Using `send=` silently
fails — no error, but synthesis nodes are never dispatched after HITL resume.

**LangGraph interrupt() requires a checkpointer** (Spec 1)
`langgraph_interrupt()` raises if no checkpointer is configured. Always pass `MemorySaver()`
explicitly when building the graph in tests. Do not rely on the default `None` checkpointer.

**TypedDict over Pydantic for LangGraph state** (Spec 1)
LangGraph reducers and `Send()` payloads work more cleanly with TypedDict than Pydantic models.
Avoid Pydantic V1/V2 compatibility issues in state by keeping all state as TypedDict.

**Budget checks must be inside agents, not only at the API layer** (Spec 1)
If budget enforcement only exists in the API layer, agents called via LangGraph `Send()` bypass
the check entirely. Each agent must check `current_total_cost >= max_budget_usd` independently.

## Process

**Break overloaded phases early** (Spec 1)
Phase 8 combined 5 deliverables (E2E tests, integration tests, fixtures, LLM eval, chat assistant).
This caused rushed test quality that reviewers flagged. Phases should have at most 2-3 deliverables.

**3-way consultation catches real bugs early** (Spec 1)
The consultation round for Phase 5 caught a `break → continue` bug in the draft retry loop
before integration tests revealed it. Phase 3 consultation caught `signal_ambiguity_score`
never being wired into Tier 2 escalation. Invest in detailed consultation prompts.

**Define "session" in the spec before implementation** (Spec 1)
"Session" appeared implicitly across spec sections (budget scoping, HITL state, API lifecycle)
without a formal definition. This caused ambiguity in state persistence design that required
3 review cycles to resolve. Add a glossary section to complex specs.

## Tooling

**LangGraph MemorySaver is test-only** (Spec 1)
`MemorySaver` does not persist across process restarts. For production, use `AsyncSqliteSaver`
with proper async context management. Ensure `async with checkpointer:` wraps the full session.

**AsyncSqliteSaver requires paired `__aenter__`/`__aexit__`** (Spec 1)
Calling `__aenter__()` without `__aexit__()` leaks the DB connection. Use `async with` syntax
or explicit try/finally cleanup.

## Integration

**`from X import Y` → patch the using module, not the source** (Spec 1)
See Testing section above. This applies to both test patches and runtime monkey-patching.

**LangGraph HITL flow: interrupt → checkpoint → resume** (Spec 1)
The HITL node must: (1) call `interrupt()` to serialize state, (2) return to the graph's caller,
(3) receive `Command(resume=...)` on re-invoke, (4) dispatch synthesis via `Command(goto=[Send(...)])`.
Each step requires the checkpointer to be active. Missing any step causes silent no-ops.

---

*Updated by Spec 1: Proactive Sales Signal Intelligence Engine (2026-03-27)*

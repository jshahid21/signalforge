# Observability: LangSmith Tracing

SignalForge uses [LangSmith](https://smith.langchain.com/) for distributed tracing of all LangGraph pipeline runs.

## What Gets Traced

When tracing is enabled, every pipeline run emits a trace to LangSmith containing:

- **Per-node spans**: `orchestrator`, `company_pipeline`, `hitl_gate`, and all sub-nodes
- **Token counts**: input/output tokens per LLM call within each node
- **Latency**: wall-clock time per node
- **HITL interrupt events**: `interrupt()` lifecycle events from the persona-selection gate

Traces are grouped under the `signalforge` project in LangSmith by default.

### Draft Feedback

When a user approves or rejects (regenerates) a draft, structured feedback is logged to LangSmith via `client.create_feedback()`:

- **Approve** → `score=1.0`, key=`draft-quality`
- **Regenerate** → `score=0.0`, key=`draft-quality`, with optional `override_reason` as comment

This ties the human-in-the-loop to LangSmith's feedback-driven analytics, enabling analysis of which prompts produce approved drafts vs. rejected ones. Feedback is a graceful no-op when tracing is disabled.

## Enabling Tracing

Set the following environment variables in your `.env` file (copy from `.env.example`):

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=<your-langsmith-api-key>
LANGCHAIN_PROJECT=signalforge
```

Get a LangSmith API key at [smith.langchain.com](https://smith.langchain.com/) → Settings → API Keys.

Tracing is **disabled by default** (`LANGCHAIN_TRACING_V2=false`). No code changes are needed — the LangChain runtime picks up these variables automatically.

## Verifying Traces

1. Start a pipeline run (e.g., via `tests/test_e2e.py` or the API).
2. Open [smith.langchain.com](https://smith.langchain.com/) → Projects → `signalforge`.
3. You should see a trace for the run with node-level spans.

## Performance Impact

Traces are submitted asynchronously in the background. Latency impact on pipeline execution is minimal for typical workloads.

## Data Sensitivity

LangSmith traces may include company names, signal summaries, and draft content. Ensure your LangSmith project access is restricted to team members with need-to-know. Do not use real customer data in evaluation seed examples.

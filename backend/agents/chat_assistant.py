"""Chat Assistant Agent — conversational Q&A scoped to a single CompanyState (spec §5.11).

Constraints:
    - Read-only: cannot trigger pipeline re-runs
    - Scoped to selected company only
    - Must not fabricate signals or research not in CompanyState
    - Responses streamed as async generator (consumed by SSE endpoint in Phase 6)

Context injection format (injected at start of each turn):
    Company: {company_name}
    Signal Summary: {qualified_signal.summary}
    Tech Stack: {research_result.tech_stack}
    Core Problem: {solution_mapping.core_problem}
    Selected Personas: {selected_persona_titles}
    Current Draft (if any): {draft subject + first 200 chars of body}
"""
from __future__ import annotations

from typing import AsyncGenerator

from backend.models.state import CompanyState
from backend.tracing import traceable


def _build_context_block(cs: CompanyState, active_persona_id: str | None = None) -> str:
    """Assemble structured context block for the assistant's system prompt."""
    parts: list[str] = [f"Company: {cs['company_name']}"]

    qualified_signal = cs.get("qualified_signal")
    if qualified_signal:
        parts.append(f"Signal Summary: {qualified_signal['summary']}")

    research_result = cs.get("research_result")
    if research_result:
        tech_stack = research_result.get("tech_stack") or []
        if tech_stack:
            parts.append(f"Tech Stack: {', '.join(tech_stack)}")
        if research_result.get("company_context"):
            parts.append(f"Company Context: {research_result['company_context']}")

    solution_mapping = cs.get("solution_mapping")
    if solution_mapping:
        parts.append(f"Core Problem: {solution_mapping['core_problem']}")
        areas = ", ".join(solution_mapping.get("solution_areas") or [])
        if areas:
            parts.append(f"Solution Areas: {areas}")
        parts.append(f"Confidence Score: {solution_mapping['confidence_score']}/100")

    selected_ids = cs.get("selected_personas") or []
    all_personas = {p["persona_id"]: p for p in cs.get("generated_personas") or []}
    selected_titles = [all_personas[pid]["title"] for pid in selected_ids if pid in all_personas]
    if selected_titles:
        parts.append(f"Selected Personas: {', '.join(selected_titles)}")

    # Active draft context
    if active_persona_id:
        drafts = cs.get("drafts") or {}
        draft = drafts.get(active_persona_id)
        if draft:
            body_preview = draft["body"][:200] + "..." if len(draft["body"]) > 200 else draft["body"]
            parts.append(f"Current Draft Subject: {draft['subject_line']}")
            parts.append(f"Current Draft Preview: {body_preview}")

    return "\n".join(parts)


_SYSTEM_PROMPT_TEMPLATE = """You are a sales intelligence assistant helping a technical seller understand their accounts.

You have read-only access to the following company intelligence. Do NOT fabricate signals, facts, or claims not present in this context.

--- COMPANY CONTEXT ---
{context_block}
--- END CONTEXT ---

You can help with:
- Explaining qualification and scoring decisions
- Suggesting alternative outreach angles or personas
- Refining tone or content of the current draft
- Answering questions about the company's technical situation

You CANNOT: trigger pipeline re-runs, fetch new data, or make decisions that require human judgment.
Keep responses concise and grounded in the provided context."""


@traceable(name="stream_chat_response")
async def stream_chat_response(
    cs: CompanyState,
    user_message: str,
    conversation_history: list[dict[str, str]],
    llm_model: str,
    llm_provider: str = "anthropic",
    active_persona_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream a chat response for the given company state and message.

    Yields text chunks as they are produced by the LLM.
    If LLM is not configured, yields a single error message.

    Args:
        cs: Company state to use as read-only context.
        user_message: The user's question or request.
        conversation_history: List of prior turns [{role, content}].
        llm_model: LLM model identifier.
        active_persona_id: Currently active persona ID (for draft context).
    """
    if not llm_model:
        yield "Chat assistant requires a configured LLM model."
        return

    try:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    except ImportError:
        yield "Chat assistant requires langchain-core. Please install dependencies."
        return

    context_block = _build_context_block(cs, active_persona_id)
    system_content = _SYSTEM_PROMPT_TEMPLATE.format(context_block=context_block)

    messages = [SystemMessage(content=system_content)]

    # Add conversation history (last 10 turns)
    for turn in conversation_history[-10:]:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    try:
        # Detect provider from model name
        from backend.config.loader import load_config
        config = load_config()
        provider = (config.api_keys.llm_provider or "").strip().lower()
        if provider in ("openai", "gpt", "chatgpt", "open_ai"):
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=llm_model, max_tokens=600, temperature=0.3)
        else:
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(model=llm_model, max_tokens=600, temperature=0.3)
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield str(chunk.content)
    except Exception as exc:
        yield f"Error generating response: {exc}"


async def get_chat_response(
    cs: CompanyState,
    user_message: str,
    conversation_history: list[dict[str, str]],
    llm_model: str,
    llm_provider: str = "anthropic",
    active_persona_id: str | None = None,
) -> str:
    """Non-streaming version of the chat response. Returns full text.

    Used for testing and non-SSE contexts.
    """
    chunks: list[str] = []
    async for chunk in stream_chat_response(
        cs=cs,
        user_message=user_message,
        conversation_history=conversation_history,
        llm_model=llm_model,
        llm_provider=llm_provider,
        active_persona_id=active_persona_id,
    ):
        chunks.append(chunk)
    return "".join(chunks)

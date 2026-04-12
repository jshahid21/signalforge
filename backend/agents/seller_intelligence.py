"""Seller Intelligence Extraction Agent — scrapes seller website and extracts structured intelligence.

Crawls the seller's public website (homepage + discovered subpages), combines page text,
and uses the configured LLM to extract structured intelligence: differentiators, sales plays,
proof points, and competitive positioning.

The extracted SellerIntelligence is saved to the seller profile config for use in draft generation.

Auto-linking: After extraction, seller intelligence items can be linked to capability map entries
via LLM-based semantic matching (auto_link_intelligence).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage

from backend.config.loader import (
    ProofPoint,
    SalesPlay,
    SellerIntelligence,
    load_config,
    save_config,
)
from backend.tracing import traceable
from backend.tools.web_crawler import (
    strip_html_tags,
    crawl_url,
    extract_links,
    fetch_html,
)

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None  # type: ignore[assignment,misc]


logger = logging.getLogger(__name__)

_MAX_COMBINED_TEXT = 30_000  # chars — fits comfortably in most LLM context windows
_SUBPAGE_CRAWL_DELAY = 1.0  # seconds between subpage fetches


def _normalized_llm_provider(llm_provider: str) -> str:
    """Return 'openai' or 'anthropic' for routing."""
    p = (llm_provider or "").strip().lower()
    if p in ("openai", "gpt", "chatgpt", "open_ai"):
        return "openai"
    return "anthropic"


def _validate_url(url: str) -> str:
    """Validate URL: must be HTTPS with a valid domain. Returns normalized URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError(
            f"URL must use HTTPS (got '{parsed.scheme}'). "
            f"Please provide a URL starting with https://"
        )
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: no domain found in '{url}'")
    return url.strip()


def _build_extraction_prompt(combined_text: str) -> str:
    """Build the LLM prompt for extracting seller intelligence from sales collateral."""
    return f"""You are analyzing B2B sales collateral (which may include website content, pitch decks, case studies, battlecards, or other sales materials) to extract structured sales intelligence.

Content:
{combined_text[:_MAX_COMBINED_TEXT]}

Extract the following four categories of intelligence from this website content.
ONLY include information that is explicitly stated or strongly implied on the website.
If a category has no supporting evidence on the site, return an empty list for it — do NOT hallucinate.

Output ONLY valid JSON in this exact format:
{{
  "differentiators": [
    "What makes this product/service unique — specific competitive advantages"
  ],
  "sales_plays": [
    {{
      "play": "A specific use case or value proposition",
      "category": "snake_case_category (e.g., cost_optimization, security_compliance, platform_scaling, data_analytics, ml_ops, devops)"
    }}
  ],
  "proof_points": [
    {{
      "customer": "Customer or company name",
      "summary": "Brief outcome or metric (e.g., 'Reduced cloud costs by 40%')"
    }}
  ],
  "competitive_positioning": [
    "How the seller differentiates from alternatives or competitors"
  ]
}}

Guidelines:
- differentiators: 3-5 items, focus on unique technical or business advantages
- sales_plays: 2-4 items, each with a problem-domain category
- proof_points: Include any customer logos, case studies, or quantified outcomes mentioned
- competitive_positioning: How they position against alternatives (may be empty if not discussed)
- Be concise — each item should be 1-2 sentences maximum"""


def _stringify_llm_content(raw: str | list[Any] | Any) -> str:
    """Normalize AIMessage.content (str or multimodal blocks) to plain text."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(raw)


def _parse_extraction_response(text: str) -> SellerIntelligence | None:
    """Parse LLM response into SellerIntelligence. Returns None on parse failure."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        return None

    try:
        differentiators = [str(d) for d in data.get("differentiators", []) if isinstance(d, str)]
        sales_plays = [
            SalesPlay(play=str(sp["play"]), category=str(sp["category"]))
            for sp in data.get("sales_plays", [])
            if isinstance(sp, dict) and "play" in sp and "category" in sp
        ]
        proof_points = [
            ProofPoint(customer=str(pp["customer"]), summary=str(pp["summary"]))
            for pp in data.get("proof_points", [])
            if isinstance(pp, dict) and "customer" in pp and "summary" in pp
        ]
        competitive_positioning = [
            str(cp) for cp in data.get("competitive_positioning", []) if isinstance(cp, str)
        ]

        return SellerIntelligence(
            differentiators=differentiators,
            sales_plays=sales_plays,
            proof_points=proof_points,
            competitive_positioning=competitive_positioning,
            last_scraped=datetime.now(timezone.utc).isoformat(),
        )
    except (TypeError, KeyError):
        return None


@traceable(name="extract_seller_intelligence")
async def extract_seller_intelligence(
    website_url: str,
    llm_provider: str,
    llm_model: str,
) -> SellerIntelligence:
    """Scrape a seller's website and extract structured intelligence using LLM.

    Args:
        website_url: HTTPS URL of the seller's website
        llm_provider: LLM provider name (e.g., "openai", "anthropic")
        llm_model: LLM model identifier

    Returns:
        SellerIntelligence with extracted data

    Raises:
        ValueError: If URL is invalid or no pages could be fetched
        RuntimeError: If LLM extraction fails
    """
    url = _validate_url(website_url)

    # Fetch homepage raw HTML for link discovery
    homepage_html = await fetch_html(url)
    if not homepage_html:
        raise ValueError(
            f"Could not fetch website at {url}. "
            "The site may be unreachable, blocking crawlers, or require JavaScript rendering."
        )

    # Extract subpage links from homepage HTML
    subpage_urls = extract_links(homepage_html, url)

    # Convert homepage HTML to text
    homepage_text = strip_html_tags(homepage_html)[:50_000]

    # Crawl discovered subpages
    page_texts = [homepage_text]
    for subpage_url in subpage_urls:
        await asyncio.sleep(_SUBPAGE_CRAWL_DELAY)
        text = await crawl_url(subpage_url)
        if text:
            page_texts.append(text)

    # Combine all page text
    combined_text = "\n\n---\n\n".join(page_texts)
    if len(combined_text) > _MAX_COMBINED_TEXT:
        combined_text = combined_text[:_MAX_COMBINED_TEXT]

    # Build prompt and call LLM
    prompt = _build_extraction_prompt(combined_text)
    route = _normalized_llm_provider(llm_provider)

    if route == "openai":
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed")
        llm = ChatOpenAI(model=llm_model.strip().lower(), max_tokens=2000, temperature=0)
    else:
        if ChatAnthropic is None:
            raise RuntimeError("langchain-anthropic not installed")
        llm = ChatAnthropic(model=llm_model.strip(), max_tokens=2000, temperature=0)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw_text = _stringify_llm_content(response.content)
    except Exception as exc:
        raise RuntimeError(f"LLM extraction call failed: {exc}") from exc

    intelligence = _parse_extraction_response(raw_text)
    if intelligence is None:
        raise RuntimeError(
            "LLM returned unparseable response. The website content may not contain "
            "enough structured information for extraction."
        )

    return intelligence


@traceable(name="extract_seller_intelligence_from_text")
async def extract_seller_intelligence_from_text(
    text: str,
    llm_provider: str,
    llm_model: str,
) -> SellerIntelligence:
    """Extract structured intelligence from pre-extracted text (documents or paste).

    Uses the same LLM extraction pipeline as website scraping but skips crawling.

    Args:
        text: Plain text content from documents or paste
        llm_provider: LLM provider name
        llm_model: LLM model identifier

    Returns:
        SellerIntelligence with extracted data

    Raises:
        ValueError: If text is empty
        RuntimeError: If LLM extraction fails
    """
    if not text or not text.strip():
        raise ValueError("No text content provided for extraction.")

    combined_text = text[:_MAX_COMBINED_TEXT]
    prompt = _build_extraction_prompt(combined_text)
    route = _normalized_llm_provider(llm_provider)

    if route == "openai":
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed")
        llm = ChatOpenAI(model=llm_model.strip().lower(), max_tokens=2000, temperature=0)
    else:
        if ChatAnthropic is None:
            raise RuntimeError("langchain-anthropic not installed")
        llm = ChatAnthropic(model=llm_model.strip(), max_tokens=2000, temperature=0)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw_text = _stringify_llm_content(response.content)
    except Exception as exc:
        raise RuntimeError(f"LLM extraction call failed: {exc}") from exc

    intelligence = _parse_extraction_response(raw_text)
    if intelligence is None:
        raise RuntimeError(
            "LLM returned unparseable response. The content may not contain "
            "enough structured information for extraction."
        )

    return intelligence


async def extract_and_save_seller_intelligence(
    website_url: str | None = None,
    text: str | None = None,
) -> SellerIntelligence:
    """Extract seller intelligence and save to config.

    Provide ``website_url`` for URL-based extraction, ``text`` for text-based
    extraction (from files or paste), or neither to use the URL from config.

    Returns the extracted SellerIntelligence.
    """
    config = load_config()

    # Determine source — text takes priority, then explicit URL, then config URL
    if text:
        source = "text"
    else:
        url = website_url or config.seller_profile.website_url
        if not url:
            raise ValueError(
                "No website URL provided and none configured in seller profile. "
                "Please provide a website URL."
            )
        source = "url"

    llm_provider = config.api_keys.llm_provider
    llm_model = config.api_keys.llm_model
    if not llm_model:
        raise ValueError(
            "LLM model is not configured. Open Settings → API Keys and set the LLM provider and model."
        )

    if source == "text":
        intelligence = await extract_seller_intelligence_from_text(text, llm_provider, llm_model)
    else:
        intelligence = await extract_seller_intelligence(url, llm_provider, llm_model)

    # Save to config
    if website_url:
        config.seller_profile.website_url = website_url
    config.seller_profile.seller_intelligence = intelligence
    save_config(config)

    # Auto-link to capability map if available
    from backend.config.capability_map import load_capability_map
    cap_map = load_capability_map()
    if cap_map and cap_map.entries:
        try:
            await auto_link_intelligence(cap_map, intelligence, llm_provider, llm_model)
            logger.info("Auto-linked seller intelligence to %d capability entries", len(cap_map.entries))
        except Exception:
            logger.warning("Auto-linking failed; capability map unchanged", exc_info=True)

    return intelligence


# ---------------------------------------------------------------------------
# Auto-linking: match seller intelligence to capability map entries
# ---------------------------------------------------------------------------

_MAX_INTELLIGENCE_ITEMS = 10  # truncate each category to avoid prompt overflow


def _build_auto_link_prompt(
    capability_entries: list[dict[str, Any]],
    intelligence: SellerIntelligence,
) -> str:
    """Build LLM prompt for matching intelligence items to capability entries."""
    entries_text = "\n".join(
        f"- id: {e['id']} | label: {e['label']} | areas: {', '.join(e.get('solution_areas', []))}"
        for e in capability_entries
    )

    diffs = intelligence.differentiators[:_MAX_INTELLIGENCE_ITEMS]
    plays = [sp.model_dump() for sp in intelligence.sales_plays[:_MAX_INTELLIGENCE_ITEMS]]
    proofs = [pp.model_dump() for pp in intelligence.proof_points[:_MAX_INTELLIGENCE_ITEMS]]

    return f"""You are matching seller intelligence to capability map entries based on semantic relevance.

Capability Map Entries:
{entries_text}

Seller Intelligence:
- Differentiators: {json.dumps(diffs)}
- Sales Plays: {json.dumps(plays)}
- Proof Points: {json.dumps(proofs)}

For each capability entry, select the differentiators, sales plays, and proof points that are most relevant.
An item can match multiple entries or no entries. Only assign items where there is clear semantic relevance.

Output ONLY valid JSON in this format:
{{
  "{capability_entries[0]['id'] if capability_entries else 'example_id'}": {{
    "differentiators": ["<matched differentiator text>"],
    "sales_plays": [{{"play": "...", "category": "..."}}],
    "proof_points": [{{"customer": "...", "summary": "..."}}]
  }}
}}

Include only entries that have at least one matched item. Omit entries with no matches."""


def _parse_auto_link_response(text: str) -> dict[str, dict[str, Any]] | None:
    """Parse LLM auto-link response. Returns mapping of entry_id → intelligence items."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        data = json.loads(text[start:end])
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


@traceable(name="auto_link_intelligence")
async def auto_link_intelligence(
    capability_map: Any,  # CapabilityMap — avoid circular import at type level
    intelligence: SellerIntelligence,
    llm_provider: str,
    llm_model: str,
) -> dict[str, dict[str, Any]]:
    """Match seller intelligence items to capability map entries using LLM.

    Updates capability map entries in-place and saves to disk.

    Returns:
        Mapping of entry_id → {differentiators, sales_plays, proof_points} for matched entries.
    """
    from backend.config.capability_map import save_capability_map

    if not capability_map.entries:
        return {}

    has_items = (
        intelligence.differentiators
        or intelligence.sales_plays
        or intelligence.proof_points
    )
    if not has_items:
        return {}

    entries_data = [e.as_dict() for e in capability_map.entries]
    prompt = _build_auto_link_prompt(entries_data, intelligence)

    route = _normalized_llm_provider(llm_provider)
    if route == "openai":
        if ChatOpenAI is None:
            raise RuntimeError("langchain-openai not installed")
        llm = ChatOpenAI(model=llm_model.strip().lower(), max_tokens=2000, temperature=0)
    else:
        if ChatAnthropic is None:
            raise RuntimeError("langchain-anthropic not installed")
        llm = ChatAnthropic(model=llm_model.strip(), max_tokens=2000, temperature=0)

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    raw_text = _stringify_llm_content(response.content)

    mapping = _parse_auto_link_response(raw_text)
    if mapping is None:
        logger.warning("Auto-link LLM returned unparseable response")
        return {}

    # Apply mapping to capability map entries
    entry_by_id = {e.id: e for e in capability_map.entries}
    for entry_id, items in mapping.items():
        entry = entry_by_id.get(entry_id)
        if entry is None:
            logger.warning("Auto-link referenced unknown capability ID: %s", entry_id)
            continue

        if isinstance(items.get("differentiators"), list):
            entry.differentiators = [str(d) for d in items["differentiators"] if isinstance(d, str)]
        if isinstance(items.get("sales_plays"), list):
            entry.sales_plays = [
                sp for sp in items["sales_plays"]
                if isinstance(sp, dict) and "play" in sp and "category" in sp
            ]
        if isinstance(items.get("proof_points"), list):
            entry.proof_points = [
                pp for pp in items["proof_points"]
                if isinstance(pp, dict) and "customer" in pp and "summary" in pp
            ]

    save_capability_map(capability_map)
    return mapping

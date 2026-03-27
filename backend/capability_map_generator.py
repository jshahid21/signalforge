"""Capability Map Generator — LLM-based generation from seller profile inputs (spec §8.1).

Three input modes (user provides one or more):
    1. product_list: Paste of SKU/service names
    2. product_url: URL to product/solutions page (crawled via web_crawler)
    3. territory: Free-text focus area description

Process:
    1. Extract product names + descriptions from inputs
    2. LLM groups products into problem-domain categories
    3. For each category, LLM generates problem_signals + solution_areas (vendor-agnostic)
    4. Output saved as capability_map.yaml

Generated map is hot-reloadable (no restart required after edits).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage
except ImportError:
    ChatAnthropic = None  # type: ignore[assignment,misc]
    HumanMessage = None  # type: ignore[assignment]


@dataclass
class CapabilityMapGeneratorInput:
    """Input for capability map generation. Provide at least one field."""
    product_list: str = ""       # Newline-separated SKU/service names
    product_url: str = ""        # URL to product/solutions page (will be crawled)
    territory: str = ""          # Free-text focus area description


def _build_generation_prompt(extracted_content: str) -> str:
    return f"""You are a technical solutions architect generating a capability map for a B2B seller.

Seller's product and territory information:
{extracted_content[:4000]}

Create a capability map that groups the seller's offerings into problem-domain categories.
For each category:
- Group related products/services into a single capability category
- Name the category after the CUSTOMER PROBLEM, not the vendor product (e.g., "Data Platform" not "Snowflake")
- Generate problem_signals: 4–6 keywords/phrases that indicate a customer has this need
  (these are signals you'd find in job postings, blog posts, or news about a company with this pain)
- Generate solution_areas: 2–4 vendor-agnostic descriptions of what the seller addresses
  (e.g., "Columnar storage optimization", NOT "Snowflake" or a product name)

Output ONLY valid JSON in this exact format:
{{
  "capabilities": [
    {{
      "id": "<snake_case_id>",
      "label": "<Human Readable Category Name>",
      "problem_signals": ["<signal1>", "<signal2>", "<signal3>", "<signal4>"],
      "solution_areas": ["<area1>", "<area2>", "<area3>"]
    }}
  ]
}}

Generate 3–6 capability categories. Be specific and actionable."""


def _parse_generation_response(text: str) -> list[dict[str, Any]]:
    """Extract capability list from LLM response. Returns [] on failure."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return []
    try:
        data = json.loads(text[start:end])
        caps = data.get("capabilities", [])
        if not isinstance(caps, list):
            return []
        valid = []
        for cap in caps:
            if not isinstance(cap, dict):
                continue
            if "id" not in cap or "label" not in cap:
                continue
            valid.append({
                "id": str(cap["id"]),
                "label": str(cap["label"]),
                "problem_signals": [str(s) for s in cap.get("problem_signals", []) if isinstance(s, str)],
                "solution_areas": [str(s) for s in cap.get("solution_areas", []) if isinstance(s, str)],
            })
        return valid
    except (json.JSONDecodeError, ValueError, TypeError):
        return []


async def generate_capability_map(
    inputs: CapabilityMapGeneratorInput,
    llm_model: str,
    llm_provider: str = "anthropic",
) -> "CapabilityMap | None":
    """Generate capability map from seller inputs. Returns None on failure.

    Crawls product_url if provided. Passes all content to LLM for grouping.
    Saves generated map to disk and returns the CapabilityMap object.
    """
    if not llm_model or ChatAnthropic is None:
        return None

    # Collect all content
    content_parts: list[str] = []

    if inputs.product_list.strip():
        content_parts.append(f"Products/Services:\n{inputs.product_list.strip()}")

    if inputs.product_url.strip():
        from backend.tools.web_crawler import crawl_url
        page_text = await crawl_url(inputs.product_url.strip())
        if page_text:
            content_parts.append(f"Product page content (from {inputs.product_url}):\n{page_text[:2000]}")

    if inputs.territory.strip():
        content_parts.append(f"Territory/Focus Area:\n{inputs.territory.strip()}")

    if not content_parts:
        return None

    extracted_content = "\n\n".join(content_parts)
    prompt = _build_generation_prompt(extracted_content)

    try:
        llm = ChatAnthropic(model=llm_model, max_tokens=2000, temperature=0)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        capabilities_data = _parse_generation_response(str(response.content))
    except Exception:
        return None

    if not capabilities_data:
        return None

    # Build CapabilityMap object and persist it
    from backend.config.capability_map import CapabilityMap, CapabilityMapEntry, save_capability_map

    entries = [CapabilityMapEntry(cap) for cap in capabilities_data]
    capability_map = CapabilityMap(entries=entries, version="1.0")
    save_capability_map(capability_map)
    return capability_map

"""Settings routes — seller profile, API keys, session budget, capability map."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config.loader import (
    SalesPlay,
    ProofPoint,
    SellerIntelligence,
    load_config,
    save_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Seller Profile
# ---------------------------------------------------------------------------


class SellerIntelligenceBody(BaseModel):
    differentiators: list[str] = Field(default_factory=list)
    sales_plays: list[SalesPlay] = Field(default_factory=list)
    proof_points: list[ProofPoint] = Field(default_factory=list)
    competitive_positioning: list[str] = Field(default_factory=list)
    last_scraped: Optional[str] = None


class SellerProfileBody(BaseModel):
    company_name: str = ""
    portfolio_summary: str = ""
    portfolio_items: list[str] = []
    website_url: Optional[str] = None
    seller_intelligence: Optional[SellerIntelligenceBody] = None


@router.get("/seller-profile")
async def get_seller_profile() -> dict:
    config = load_config()
    return config.seller_profile.model_dump()


@router.put("/seller-profile")
async def update_seller_profile(body: SellerProfileBody) -> dict:
    config = load_config()
    config.seller_profile.company_name = body.company_name
    config.seller_profile.portfolio_summary = body.portfolio_summary
    config.seller_profile.portfolio_items = body.portfolio_items
    if body.website_url is not None:
        config.seller_profile.website_url = body.website_url
    if body.seller_intelligence is not None:
        config.seller_profile.seller_intelligence = SellerIntelligence(
            **body.seller_intelligence.model_dump()
        )
    save_config(config)
    return {"status": "saved", "seller_profile": config.seller_profile.model_dump()}


# ---------------------------------------------------------------------------
# Seller Intelligence Extraction
# ---------------------------------------------------------------------------


class ExtractIntelligenceRequest(BaseModel):
    website_url: Optional[str] = None


@router.post("/seller-intelligence/extract")
async def extract_seller_intelligence(body: ExtractIntelligenceRequest) -> dict:
    """Extract seller intelligence from website. Saves to config on success."""
    from backend.agents.seller_intelligence import extract_and_save_seller_intelligence

    try:
        intelligence = await extract_and_save_seller_intelligence(
            website_url=body.website_url,
        )
        return {
            "status": "extracted",
            "seller_intelligence": intelligence.model_dump(),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class ApiKeysBody(BaseModel):
    jsearch: str = ""
    tavily: str = ""
    llm_provider: str = ""
    llm_model: str = ""


@router.get("/api-keys")
async def get_api_keys() -> dict:
    config = load_config()
    data = config.api_keys.model_dump()
    # Mask all keys except the provider/model fields
    for key in ("jsearch", "tavily"):
        if data.get(key):
            data[key] = "***" + data[key][-4:] if len(data[key]) > 4 else "***"
    return data


@router.put("/api-keys")
async def update_api_keys(body: ApiKeysBody) -> dict:
    config = load_config()
    # Only update non-empty values to avoid accidentally clearing keys
    if body.jsearch:
        config.api_keys.jsearch = body.jsearch
    if body.tavily:
        config.api_keys.tavily = body.tavily
    if body.llm_provider:
        config.api_keys.llm_provider = body.llm_provider
    if body.llm_model:
        config.api_keys.llm_model = body.llm_model
    save_config(config)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Session Budget
# ---------------------------------------------------------------------------


class SessionBudgetBody(BaseModel):
    max_usd: float = 0.50
    tier3_limit: int = 1


@router.get("/session-budget")
async def get_session_budget() -> dict:
    config = load_config()
    return config.session_budget.model_dump()


@router.put("/session-budget")
async def update_session_budget(body: SessionBudgetBody) -> dict:
    if body.max_usd <= 0:
        raise HTTPException(status_code=422, detail="max_usd must be positive")
    if body.tier3_limit < 0:
        raise HTTPException(status_code=422, detail="tier3_limit must be non-negative")
    config = load_config()
    config.session_budget.max_usd = body.max_usd
    config.session_budget.tier3_limit = body.tier3_limit
    save_config(config)
    return {"status": "saved", "session_budget": config.session_budget.model_dump()}


# ---------------------------------------------------------------------------
# Capability Map Generation
# ---------------------------------------------------------------------------


class CapabilityMapRequest(BaseModel):
    # Frontend sends newline-separated text for product_list; allow list for API clients
    product_list: str | list[str] | None = None
    product_url: Optional[str] = None
    territory_text: Optional[str] = None


class CapabilityMapEntryBody(BaseModel):
    id: str
    label: str
    problem_signals: list[str] = []
    solution_areas: list[str] = []


@router.get("/capability-map")
async def get_capability_map() -> list[dict]:
    """Return the current capability map entries."""
    from backend.config.capability_map import load_capability_map

    cap_map = load_capability_map()
    if cap_map is None:
        return []
    return [e.as_dict() for e in cap_map.entries]


@router.post("/capability-map/entries", status_code=201)
async def add_capability_map_entry(body: CapabilityMapEntryBody) -> dict:
    """Add a new entry to the capability map."""
    from backend.config.capability_map import (
        CapabilityMap,
        CapabilityMapEntry,
        load_capability_map,
        save_capability_map,
    )

    cap_map = load_capability_map()
    entries = list(cap_map.entries) if cap_map else []

    if any(e.id == body.id for e in entries):
        raise HTTPException(status_code=409, detail=f"Entry with id '{body.id}' already exists")

    new_entry = CapabilityMapEntry({
        "id": body.id,
        "label": body.label,
        "problem_signals": body.problem_signals,
        "solution_areas": body.solution_areas,
    })
    entries.append(new_entry)
    version = cap_map.version if cap_map else "1.0"
    save_capability_map(CapabilityMap(entries, version=version))
    return new_entry.as_dict()


@router.delete("/capability-map/entries/{entry_id}", status_code=200)
async def delete_capability_map_entry(entry_id: str) -> dict:
    """Delete an entry from the capability map by id."""
    from backend.config.capability_map import (
        CapabilityMap,
        load_capability_map,
        save_capability_map,
    )

    cap_map = load_capability_map()
    if cap_map is None:
        raise HTTPException(status_code=404, detail="Capability map not found")

    entries = [e for e in cap_map.entries if e.id != entry_id]
    if len(entries) == len(cap_map.entries):
        raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found")

    save_capability_map(CapabilityMap(entries, version=cap_map.version))
    return {"status": "deleted", "id": entry_id}


def _product_list_as_str(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(x) for x in value)
    return str(value)


@router.post("/capability-map/generate", status_code=202)
async def generate_capability_map(body: CapabilityMapRequest) -> dict:
    """Generate and save a capability map from seller profile inputs.

    Runs the CapabilityMapGenerator LLM agent to produce a capability_map.yaml
    saved to ~/.signalforge/capability_map.yaml.
    """
    from backend.capability_map_generator import (
        CapabilityMapGeneratorInput,
        generate_capability_map as _generate,
    )

    config = load_config()

    if not (config.api_keys.llm_model or "").strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "LLM model is not set. Open Settings → API Keys and set LLM provider and model "
                "(OpenAI: set provider to openai / gpt / chatgpt and model e.g. gpt-4o-mini; "
                "ensure OPENAI_API_KEY is set for the backend. Anthropic: set ANTHROPIC_API_KEY.)"
            ),
        )

    inputs = CapabilityMapGeneratorInput(
        product_list=_product_list_as_str(body.product_list),
        product_url=(body.product_url or ""),
        territory=(body.territory_text or ""),
    )

    capability_map = await _generate(
        inputs,
        llm_model=config.api_keys.llm_model.strip(),
        llm_provider=config.api_keys.llm_provider,
    )
    if capability_map is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Capability map generation failed. Common causes: no usable input "
                "(product list, URL, or territory text), missing or invalid OPENAI_API_KEY / "
                "ANTHROPIC_API_KEY, wrong model id for your provider, or the model returned "
                "unparseable JSON. Check the backend terminal for errors."
            ),
        )

    # Generator already persists via save_capability_map; response uses .entries
    return {
        "status": "generated",
        "capability_count": len(capability_map.entries),
        "capabilities": [
            {"id": c.id, "label": c.label}
            for c in capability_map.entries
        ],
    }

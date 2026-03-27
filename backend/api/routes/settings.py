"""Settings routes — seller profile, API keys, session budget, capability map."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config.loader import (
    load_config,
    save_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Seller Profile
# ---------------------------------------------------------------------------


class SellerProfileBody(BaseModel):
    company_name: str = ""
    portfolio_summary: str = ""
    portfolio_items: list[str] = []


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
    save_config(config)
    return {"status": "saved", "seller_profile": config.seller_profile.model_dump()}


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
    product_list: Optional[list[str]] = None
    product_url: Optional[str] = None
    territory_text: Optional[str] = None


@router.post("/capability-map/generate", status_code=202)
async def generate_capability_map(body: CapabilityMapRequest) -> dict:
    """Generate and save a capability map from seller profile inputs.

    Runs the CapabilityMapGenerator LLM agent to produce a capability_map.yaml
    saved to ~/.signalforge/capability_map.yaml.
    """
    from backend.capability_map_generator import (
        CapabilityMapGeneratorInput,
        generate_capability_map as _generate,
        save_capability_map,
    )

    config = load_config()

    inputs = CapabilityMapGeneratorInput(
        product_list=body.product_list,
        product_url=body.product_url,
        territory_text=body.territory_text,
    )

    capability_map = await _generate(inputs, llm_model=config.api_keys.llm_model)
    if capability_map is None:
        raise HTTPException(
            status_code=422,
            detail="Capability map generation failed. Check LLM model configuration.",
        )

    save_capability_map(capability_map)
    return {
        "status": "generated",
        "capability_count": len(capability_map.capabilities),
        "capabilities": [
            {"id": c.id, "label": c.label}
            for c in capability_map.capabilities
        ],
    }

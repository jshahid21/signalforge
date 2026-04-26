"""Settings routes — seller profile, API keys, session budget, capability map."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.config.loader import (
    SalesPlay,
    ProofPoint,
    SellerIntelligence,
    apply_langsmith_env,
    load_config,
    save_config,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Seller Profile
# ---------------------------------------------------------------------------


class SellerIntelligenceBody(BaseModel):
    """Request body mirror of SellerIntelligence (used in PUT /seller-profile)."""

    differentiators: list[str] = Field(default_factory=list)
    sales_plays: list[SalesPlay] = Field(default_factory=list)
    proof_points: list[ProofPoint] = Field(default_factory=list)
    competitive_positioning: list[str] = Field(default_factory=list)
    last_scraped: Optional[str] = None


class SellerProfileBody(BaseModel):
    """Body for PUT /seller-profile — full seller-profile replacement."""

    company_name: str = ""
    portfolio_summary: str = ""
    portfolio_items: list[str] = []
    website_url: Optional[str] = None
    seller_intelligence: Optional[SellerIntelligenceBody] = None


@router.get("/seller-profile")
async def get_seller_profile() -> dict:
    """Return the current seller profile from config."""
    config = load_config()
    return config.seller_profile.model_dump()


@router.put("/seller-profile")
async def update_seller_profile(body: SellerProfileBody) -> dict:
    """Replace the seller-profile fields in config and persist to disk."""
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
# Seller Context (additional fields)
# ---------------------------------------------------------------------------


class SellerContextBody(BaseModel):
    """Body for PUT /seller-context — supplementary targeting + messaging fields."""

    target_verticals: list[str] = Field(default_factory=list)
    value_metrics: list[str] = Field(default_factory=list)
    competitive_counters: dict[str, list[str]] = Field(default_factory=dict)
    company_size_messaging: dict[str, str] = Field(default_factory=dict)


@router.get("/seller-context")
async def get_seller_context() -> dict:
    """Return supplementary seller-context fields (verticals, value metrics, competitive notes)."""
    config = load_config()
    return {
        "target_verticals": config.seller_profile.target_verticals,
        "value_metrics": config.seller_profile.value_metrics,
        "competitive_counters": config.seller_profile.competitive_counters,
        "company_size_messaging": config.seller_profile.company_size_messaging,
    }


@router.put("/seller-context")
async def update_seller_context(body: SellerContextBody) -> dict:
    """Replace the supplementary seller-context fields and persist to disk."""
    config = load_config()
    config.seller_profile.target_verticals = body.target_verticals
    config.seller_profile.value_metrics = body.value_metrics
    config.seller_profile.competitive_counters = body.competitive_counters
    config.seller_profile.company_size_messaging = body.company_size_messaging
    save_config(config)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Seller Intelligence Extraction
# ---------------------------------------------------------------------------


class ExtractIntelligenceRequest(BaseModel):
    """Body for POST /seller-intelligence/extract — provide exactly one of url or text."""

    website_url: Optional[str] = None
    text: Optional[str] = None


@router.post("/seller-intelligence/extract")
async def extract_seller_intelligence(body: ExtractIntelligenceRequest) -> dict:
    """Extract seller intelligence from website URL or pasted text.

    Provide exactly one of ``website_url`` or ``text``.
    """
    from backend.agents.seller_intelligence import extract_and_save_seller_intelligence

    if body.website_url and body.text:
        raise HTTPException(
            status_code=422,
            detail="Provide either website_url or text, not both.",
        )

    try:
        intelligence = await extract_and_save_seller_intelligence(
            website_url=body.website_url,
            text=body.text,
        )
        source_type = "text" if body.text else "url"
        return {
            "status": "extracted",
            "seller_intelligence": intelligence.model_dump(),
            "source_type": source_type,
        }
    except ValueError as exc:
        detail = str(exc)
        # Friendly message for 403 / crawler-blocked errors
        if "blocking" in detail.lower() or "403" in detail or "could not fetch" in detail.lower():
            detail = (
                "Your website blocked our crawler (common for enterprise sites). "
                "Try uploading a pitch deck or case study PDF instead."
            )
        raise HTTPException(status_code=422, detail=detail)
    except RuntimeError as exc:
        detail = str(exc)
        if "could not fetch" in detail.lower() or "unreachable" in detail.lower():
            detail = (
                "Your website blocked our crawler (common for enterprise sites). "
                "Try uploading a pitch deck or case study PDF instead."
            )
        raise HTTPException(status_code=502, detail=detail)


@router.post("/seller-intelligence/extract-from-files")
async def extract_from_files(files: list[UploadFile]) -> dict:
    """Extract seller intelligence from uploaded files (PDF, DOCX, PPTX, XLSX, HTML, TXT).

    Accepts multipart file upload. Max 5 files, 50 MB each.
    """
    from backend.agents.seller_intelligence import extract_and_save_seller_intelligence
    from backend.tools.document_parser import (
        ALLOWED_EXTENSIONS,
        MAX_FILE_SIZE,
        MAX_FILES,
        extract_text_from_files,
    )
    from pathlib import PurePath

    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"Too many files. Maximum {MAX_FILES} files allowed.",
        )

    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    file_data: list[tuple[bytes, str]] = []
    for f in files:
        ext = PurePath(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Accepted: PDF, DOCX, PPTX, XLSX, HTML, TXT",
            )
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: '{f.filename}'. Maximum 50MB per file.",
            )
        file_data.append((content, f.filename or "unknown"))

    combined_text = extract_text_from_files(file_data)
    if not combined_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the uploaded files.",
        )

    try:
        intelligence = await extract_and_save_seller_intelligence(text=combined_text)
        return {
            "status": "extracted",
            "seller_intelligence": intelligence.model_dump(),
            "source_type": "files",
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Auto-Link Intelligence to Capability Map
# ---------------------------------------------------------------------------


@router.post("/capability-map/auto-link")
async def auto_link_capability_intelligence() -> dict:
    """Trigger auto-linking of seller intelligence to capability map entries.

    Uses LLM to match scraped differentiators, sales plays, and proof points
    to the most relevant capability entries.
    """
    from backend.agents.seller_intelligence import auto_link_intelligence
    from backend.config.capability_map import load_capability_map

    config = load_config()
    cap_map = load_capability_map()
    if cap_map is None or not cap_map.entries:
        raise HTTPException(
            status_code=422,
            detail="No capability map configured. Create or generate a capability map first.",
        )

    intelligence = config.seller_profile.seller_intelligence
    has_items = (
        intelligence.differentiators
        or intelligence.sales_plays
        or intelligence.proof_points
    )
    if not has_items:
        raise HTTPException(
            status_code=422,
            detail="No seller intelligence available. Extract intelligence from your website first.",
        )

    llm_model = config.api_keys.llm_model
    if not llm_model:
        raise HTTPException(
            status_code=422,
            detail="LLM model is not configured. Open Settings → API Keys and set LLM provider and model.",
        )

    try:
        mapping = await auto_link_intelligence(
            cap_map, intelligence, config.api_keys.llm_provider, llm_model,
        )

        # Compute unlinked items (intelligence items not matched to any entry)
        linked_diffs: set[str] = set()
        linked_plays: set[str] = set()
        linked_proofs: set[str] = set()
        for items in mapping.values():
            for d in items.get("differentiators", []):
                if isinstance(d, str):
                    linked_diffs.add(d)
            for sp in items.get("sales_plays", []):
                if isinstance(sp, dict):
                    linked_plays.add(sp.get("play", ""))
            for pp in items.get("proof_points", []):
                if isinstance(pp, dict):
                    linked_proofs.add(pp.get("customer", ""))

        unlinked = {
            "differentiators": [d for d in intelligence.differentiators if d not in linked_diffs],
            "sales_plays": [sp.model_dump() for sp in intelligence.sales_plays if sp.play not in linked_plays],
            "proof_points": [pp.model_dump() for pp in intelligence.proof_points if pp.customer not in linked_proofs],
        }

        return {
            "status": "linked",
            "linked": mapping,
            "unlinked": unlinked,
            "entries_updated": len(mapping),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Auto-linking failed: {exc}")


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class ApiKeysBody(BaseModel):
    """Body for PUT /api-keys — empty fields are ignored to avoid clearing existing values."""

    jsearch: str = ""
    tavily: str = ""
    llm_provider: str = ""
    llm_model: str = ""


@router.get("/api-keys")
async def get_api_keys() -> dict:
    """Return API key configuration with provider keys masked (last 4 chars only)."""
    config = load_config()
    data = config.api_keys.model_dump()
    # Mask all keys except the provider/model fields
    for key in ("jsearch", "tavily"):
        if data.get(key):
            data[key] = "***" + data[key][-4:] if len(data[key]) > 4 else "***"
    return data


@router.put("/api-keys")
async def update_api_keys(body: ApiKeysBody) -> dict:
    """Update non-empty API key / LLM-selection fields (empty fields are ignored)."""
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
    """Body for PUT /session-budget — per-session cost ceiling and Tier 3 escalation cap."""

    max_usd: float = 0.50
    tier3_limit: int = 1


@router.get("/session-budget")
async def get_session_budget() -> dict:
    """Return the per-session cost ceiling and Tier 3 escalation cap."""
    config = load_config()
    return config.session_budget.model_dump()


@router.put("/session-budget")
async def update_session_budget(body: SessionBudgetBody) -> dict:
    """Update the per-session cost ceiling and Tier 3 escalation cap (validated)."""
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
# LangSmith Tracing
# ---------------------------------------------------------------------------


class LangSmithBody(BaseModel):
    """Body for PUT /langsmith — masked api_key values (``***...``) are ignored on update."""

    enabled: bool = False
    api_key: str = ""
    project: str = "signalforge"


@router.get("/langsmith")
async def get_langsmith() -> dict:
    """Return LangSmith tracing settings with the API key masked."""
    config = load_config()
    data = config.langsmith.model_dump()
    # Mask API key
    if data.get("api_key"):
        data["api_key"] = "***" + data["api_key"][-4:] if len(data["api_key"]) > 4 else "***"
    return data


@router.put("/langsmith")
async def update_langsmith(body: LangSmithBody) -> dict:
    """Update LangSmith settings and re-apply the LANGCHAIN_* env vars in-process."""
    config = load_config()
    config.langsmith.enabled = body.enabled
    if body.api_key and not body.api_key.startswith("***"):
        config.langsmith.api_key = body.api_key
    if body.project:
        config.langsmith.project = body.project
    save_config(config)
    apply_langsmith_env(config)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Capability Map Generation
# ---------------------------------------------------------------------------


class CapabilityIntelligenceBody(BaseModel):
    """Partial-update body for a capability map entry's intelligence fields (None = leave unchanged)."""

    differentiators: Optional[list[str]] = None
    sales_plays: Optional[list[dict]] = None
    proof_points: Optional[list[dict]] = None


@router.patch("/capability-map/{entry_id}/intelligence")
async def update_capability_intelligence(entry_id: str, body: CapabilityIntelligenceBody) -> dict:
    """Update seller intelligence fields for a specific capability map entry."""
    from backend.config.capability_map import load_capability_map, save_capability_map

    cap_map = load_capability_map()
    if cap_map is None:
        raise HTTPException(status_code=404, detail="Capability map not found")

    entry = next((e for e in cap_map.entries if e.id == entry_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry '{entry_id}' not found")

    if body.differentiators is not None:
        entry.differentiators = body.differentiators
    if body.sales_plays is not None:
        entry.sales_plays = body.sales_plays
    if body.proof_points is not None:
        entry.proof_points = body.proof_points

    save_capability_map(cap_map)
    return {"status": "updated", "entry": entry.as_dict()}


class CapabilityMapRequest(BaseModel):
    """Inputs for LLM-based capability map generation (provide one or more sources)."""

    # Frontend sends newline-separated text for product_list; allow list for API clients
    product_list: str | list[str] | None = None
    product_url: Optional[str] = None
    territory_text: Optional[str] = None


class CapabilityMapEntryBody(BaseModel):
    """Body shape for creating or replacing a single capability map entry."""

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

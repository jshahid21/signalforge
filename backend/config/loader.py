"""Config loader for SignalForge.

Config file: ~/.signalforge/config.json
First-run detection: config missing or seller_profile.company_name is empty.

LangSmith Observability (env vars — NOT loaded here, consumed by LangChain runtime):
  LANGCHAIN_TRACING_V2=true        Enable distributed tracing to LangSmith
  LANGCHAIN_ENDPOINT=...           LangSmith API endpoint (default: https://api.smith.langchain.com)
  LANGCHAIN_API_KEY=...            LangSmith API key
  LANGCHAIN_PROJECT=signalforge    LangSmith project name for trace grouping

These variables are read directly by the LangGraph/LangChain instrumentation layer
and do not need to be loaded via load_config(). Set them in .env or the shell
environment. See docs/observability.md for setup instructions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SalesPlay(BaseModel):
    """A named go-to-market play extracted from seller intelligence."""

    play: str
    category: str


class ProofPoint(BaseModel):
    """A customer reference / case study used to back a sales play."""

    customer: str
    summary: str


class SellerIntelligence(BaseModel):
    """Structured intelligence about the seller (extracted from website or pasted text)."""

    differentiators: list[str] = Field(default_factory=list)
    sales_plays: list[SalesPlay] = Field(default_factory=list)
    proof_points: list[ProofPoint] = Field(default_factory=list)
    competitive_positioning: list[str] = Field(default_factory=list)
    last_scraped: Optional[str] = None


class SellerProfileConfig(BaseModel):
    """Seller-side context: company identity, portfolio, intelligence, and outreach signals."""

    company_name: str = ""
    portfolio_summary: str = ""
    portfolio_items: list[str] = Field(default_factory=list)
    website_url: Optional[str] = None
    seller_intelligence: SellerIntelligence = Field(default_factory=SellerIntelligence)
    target_verticals: list[str] = Field(default_factory=list)
    value_metrics: list[str] = Field(default_factory=list)
    competitive_counters: dict[str, list[str]] = Field(default_factory=dict)
    company_size_messaging: dict[str, str] = Field(default_factory=dict)


class ApiKeysConfig(BaseModel):
    """Provider credentials and the active LLM provider/model selection."""

    jsearch: str = ""
    tavily: str = ""
    llm_provider: str = ""
    llm_model: str = ""


class SessionBudgetConfig(BaseModel):
    """Per-session cost guardrails: total USD ceiling and Tier 3 escalation cap."""

    max_usd: float = 0.50
    tier3_limit: int = 1


class LangSmithConfig(BaseModel):
    """LangSmith tracing settings — enables observability when ``enabled=True``."""

    enabled: bool = False
    api_key: str = ""
    project: str = "signalforge"


class SignalForgeConfig(BaseModel):
    """Top-level SignalForge configuration persisted to ``~/.signalforge/config.json``."""

    seller_profile: SellerProfileConfig = Field(default_factory=SellerProfileConfig)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)
    session_budget: SessionBudgetConfig = Field(default_factory=SessionBudgetConfig)
    langsmith: LangSmithConfig = Field(default_factory=LangSmithConfig)
    capability_map_path: str = str(Path.home() / ".signalforge" / "capability_map.yaml")


def _config_path() -> Path:
    """Return path to config file, respecting SIGNALFORGE_CONFIG_DIR env var for testing."""
    config_dir = os.environ.get("SIGNALFORGE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / "config.json"
    return Path.home() / ".signalforge" / "config.json"


def load_config() -> SignalForgeConfig:
    """Load config from disk, creating defaults if not present."""
    path = _config_path()
    if not path.exists():
        config = SignalForgeConfig()
        save_config(config)
        return config

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SignalForgeConfig.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Config file at {path} is malformed: {exc}") from exc


def save_config(config: SignalForgeConfig) -> None:
    """Persist config to disk."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def apply_langsmith_env(config: SignalForgeConfig | None = None) -> None:
    """Sync LangSmith config to environment variables consumed by LangChain runtime.

    Call on app startup and whenever LangSmith settings are saved.
    """
    if config is None:
        config = load_config()
    ls = config.langsmith
    if ls.enabled and ls.api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = ls.api_key
        os.environ["LANGCHAIN_PROJECT"] = ls.project or "signalforge"
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ.pop("LANGCHAIN_API_KEY", None)


def is_first_run() -> bool:
    """Return True if config is missing or seller profile is unconfigured."""
    path = _config_path()
    if not path.exists():
        return True
    try:
        config = load_config()
        return not config.seller_profile.company_name.strip()
    except ValueError:
        return True

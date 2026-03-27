"""Config loader for SignalForge.

Config file: ~/.signalforge/config.json
First-run detection: config missing or seller_profile.company_name is empty.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SellerProfileConfig(BaseModel):
    company_name: str = ""
    portfolio_summary: str = ""
    portfolio_items: list[str] = Field(default_factory=list)


class ApiKeysConfig(BaseModel):
    jsearch: str = ""
    tavily: str = ""
    llm_provider: str = ""
    llm_model: str = ""


class SessionBudgetConfig(BaseModel):
    max_usd: float = 0.50
    tier3_limit: int = 1


class SignalForgeConfig(BaseModel):
    seller_profile: SellerProfileConfig = Field(default_factory=SellerProfileConfig)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)
    session_budget: SessionBudgetConfig = Field(default_factory=SessionBudgetConfig)
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

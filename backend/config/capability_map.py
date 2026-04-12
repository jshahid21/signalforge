"""Capability map loader with hot-reload support.

The capability map is a YAML file at ~/.signalforge/capability_map.yaml (configurable).
It is re-read on every load_capability_map() call — no caching — so changes take effect
on the next pipeline run without requiring a restart.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .loader import load_config


class CapabilityMapEntry:
    __slots__ = (
        "id", "label", "problem_signals", "solution_areas",
        "differentiators", "sales_plays", "proof_points",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        if "id" not in data:
            raise ValueError(f"Capability map entry missing required field 'id': {data}")
        if "label" not in data:
            raise ValueError(f"Capability map entry missing required field 'label': {data}")
        self.id: str = data["id"]
        self.label: str = data["label"]
        self.problem_signals: list[str] = data.get("problem_signals") or []
        self.solution_areas: list[str] = data.get("solution_areas") or []
        self.differentiators: list[str] = data.get("differentiators") or []
        self.sales_plays: list[dict[str, str]] = data.get("sales_plays") or []
        self.proof_points: list[dict[str, str]] = data.get("proof_points") or []

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "problem_signals": self.problem_signals,
            "solution_areas": self.solution_areas,
            "differentiators": self.differentiators,
            "sales_plays": self.sales_plays,
            "proof_points": self.proof_points,
        }


class CapabilityMap:
    def __init__(self, entries: list[CapabilityMapEntry], version: str = "1.0") -> None:
        self.entries = entries
        self.version = version

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "capabilities": [e.as_dict() for e in self.entries],
        }

    def all_keywords(self) -> list[str]:
        """Flatten all problem_signals across all entries (used for deterministic scoring)."""
        keywords: list[str] = []
        for entry in self.entries:
            keywords.extend(entry.problem_signals)
        return keywords


def _map_path() -> Path:
    """Return the capability map path from config or env override."""
    override = os.environ.get("SIGNALFORGE_CAPABILITY_MAP_PATH")
    if override:
        return Path(override)
    config = load_config()
    return Path(config.capability_map_path).expanduser()


def load_capability_map() -> CapabilityMap | None:
    """Load capability map from disk. Returns None if file does not exist.

    Hot-reload: re-reads the file on every call. No caching.
    """
    path = _map_path()
    if not path.exists():
        return None

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Capability map at {path} is malformed YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Capability map at {path} must be a YAML mapping, got {type(data)}")

    raw_caps = data.get("capabilities")
    if not isinstance(raw_caps, list):
        raise ValueError(
            f"Capability map at {path} must have a 'capabilities' list, got {type(raw_caps)}"
        )

    entries = [CapabilityMapEntry(entry) for entry in raw_caps]
    version = str(data.get("version", "1.0"))
    return CapabilityMap(entries=entries, version=version)


def save_capability_map(capability_map: CapabilityMap) -> None:
    """Persist capability map to disk."""
    path = _map_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(capability_map.as_dict(), default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

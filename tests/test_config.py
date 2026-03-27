"""Tests for backend/config/ — loader, seller profile, and capability map."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from backend.config.loader import (
    SignalForgeConfig,
    is_first_run,
    load_config,
    save_config,
)
from backend.config.capability_map import (
    CapabilityMap,
    CapabilityMapEntry,
    load_capability_map,
    save_capability_map,
)
from backend.config.seller_profile import get_seller_profile, update_seller_profile


# ---------------------------------------------------------------------------
# Config loader tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_creates_default_config_on_first_run(self, tmp_config_dir: Path) -> None:
        config = load_config()
        assert isinstance(config, SignalForgeConfig)
        assert config.seller_profile.company_name == ""
        assert config.session_budget.max_usd == 0.50
        assert config.session_budget.tier3_limit == 1

    def test_config_file_written_to_disk_on_first_run(self, tmp_config_dir: Path) -> None:
        load_config()
        config_file = tmp_config_dir / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert "seller_profile" in data
        assert "api_keys" in data
        assert "session_budget" in data

    def test_round_trips_config(self, tmp_config_dir: Path) -> None:
        original = load_config()
        original.seller_profile.company_name = "Oracle Cloud Infrastructure"
        original.api_keys.jsearch = "test-key"
        save_config(original)

        loaded = load_config()
        assert loaded.seller_profile.company_name == "Oracle Cloud Infrastructure"
        assert loaded.api_keys.jsearch == "test-key"

    def test_raises_on_malformed_json(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.json"
        config_file.write_text("not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed"):
            load_config()

    def test_unknown_fields_are_ignored(self, tmp_config_dir: Path) -> None:
        config_file = tmp_config_dir / "config.json"
        config_file.write_text(
            json.dumps({"seller_profile": {}, "api_keys": {}, "unknown_field": 42}),
            encoding="utf-8",
        )
        config = load_config()
        assert isinstance(config, SignalForgeConfig)


class TestIsFirstRun:
    def test_true_when_config_missing(self, tmp_config_dir: Path) -> None:
        assert is_first_run() is True

    def test_true_when_company_name_empty(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.seller_profile.company_name = ""
        save_config(config)
        assert is_first_run() is True

    def test_false_when_company_name_set(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.seller_profile.company_name = "Acme Corp"
        save_config(config)
        assert is_first_run() is False

    def test_true_on_malformed_config(self, tmp_config_dir: Path) -> None:
        (tmp_config_dir / "config.json").write_text("bad", encoding="utf-8")
        assert is_first_run() is True


# ---------------------------------------------------------------------------
# Seller profile tests
# ---------------------------------------------------------------------------


class TestSellerProfile:
    def test_get_returns_default_profile(self, tmp_config_dir: Path) -> None:
        profile = get_seller_profile()
        assert profile.company_name == ""
        assert profile.portfolio_items == []

    def test_update_persists_profile(self, tmp_config_dir: Path) -> None:
        profile = update_seller_profile(
            company_name="Oracle Cloud Infrastructure",
            portfolio_summary="Cloud infrastructure and data services",
            portfolio_items=["OCI Compute", "Autonomous DB", "OCI Data Flow"],
        )
        assert profile.company_name == "Oracle Cloud Infrastructure"

        # Reload from disk and verify persistence
        reloaded = get_seller_profile()
        assert reloaded.company_name == "Oracle Cloud Infrastructure"
        assert reloaded.portfolio_items == ["OCI Compute", "Autonomous DB", "OCI Data Flow"]


# ---------------------------------------------------------------------------
# Capability map tests
# ---------------------------------------------------------------------------


VALID_MAP_YAML = """
version: "1.0"
generated_from: "seller_profile"
capabilities:
  - id: "data_platform_scalability"
    label: "Data Platform Scalability"
    problem_signals:
      - "scaling data warehouse to petabyte range"
      - "slow query times on large analytical datasets"
    solution_areas:
      - "Distributed query execution"
      - "Columnar storage optimization"
  - id: "ml_infra"
    label: "ML Infrastructure"
    problem_signals:
      - "deploying ML models at scale"
      - "reducing GPU cost for model training"
    solution_areas:
      - "Managed model training"
      - "Inference optimization"
"""


class TestCapabilityMapLoader:
    def test_returns_none_when_file_missing(self, tmp_capability_map_path: Path) -> None:
        assert load_capability_map() is None

    def test_loads_valid_map(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        tmp_capability_map_path.write_text(VALID_MAP_YAML, encoding="utf-8")
        cap_map = load_capability_map()
        assert cap_map is not None
        assert len(cap_map.entries) == 2
        assert cap_map.entries[0].id == "data_platform_scalability"
        assert cap_map.entries[1].id == "ml_infra"

    def test_hot_reload_reads_updated_file(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        tmp_capability_map_path.write_text(VALID_MAP_YAML, encoding="utf-8")
        map_v1 = load_capability_map()
        assert map_v1 is not None
        assert len(map_v1.entries) == 2

        # Overwrite with a map containing only 1 entry
        updated = """
version: "1.1"
capabilities:
  - id: "ml_infra"
    label: "ML Infrastructure"
    problem_signals: []
    solution_areas: []
"""
        tmp_capability_map_path.write_text(updated, encoding="utf-8")
        map_v2 = load_capability_map()
        assert map_v2 is not None
        assert len(map_v2.entries) == 1

    def test_raises_on_malformed_yaml(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        tmp_capability_map_path.write_text(":\tbad\nyaml: [", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed YAML"):
            load_capability_map()

    def test_raises_on_missing_capabilities_key(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        tmp_capability_map_path.write_text("version: '1.0'\nfoo: bar\n", encoding="utf-8")
        with pytest.raises(ValueError, match="capabilities"):
            load_capability_map()

    def test_raises_on_entry_missing_id(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        bad_yaml = "capabilities:\n  - label: 'No ID'\n"
        tmp_capability_map_path.write_text(bad_yaml, encoding="utf-8")
        with pytest.raises(ValueError, match="missing required field 'id'"):
            load_capability_map()

    def test_raises_on_entry_missing_label(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        bad_yaml = "capabilities:\n  - id: 'some_id'\n"
        tmp_capability_map_path.write_text(bad_yaml, encoding="utf-8")
        with pytest.raises(ValueError, match="missing required field 'label'"):
            load_capability_map()

    def test_entry_optional_fields_default_to_empty(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        minimal_yaml = "capabilities:\n  - id: 'x'\n    label: 'X'\n"
        tmp_capability_map_path.write_text(minimal_yaml, encoding="utf-8")
        cap_map = load_capability_map()
        assert cap_map is not None
        entry = cap_map.entries[0]
        assert entry.problem_signals == []
        assert entry.solution_areas == []

    def test_all_keywords_flattens_problem_signals(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        tmp_capability_map_path.write_text(VALID_MAP_YAML, encoding="utf-8")
        cap_map = load_capability_map()
        assert cap_map is not None
        keywords = cap_map.all_keywords()
        assert "scaling data warehouse to petabyte range" in keywords
        assert "deploying ML models at scale" in keywords
        assert len(keywords) == 4  # 2 + 2


class TestCapabilityMapSave:
    def test_round_trips_to_disk(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        entries = [
            CapabilityMapEntry(
                {"id": "test_cap", "label": "Test Cap", "problem_signals": ["foo"], "solution_areas": ["bar"]}
            )
        ]
        cap_map = CapabilityMap(entries=entries, version="1.0")
        save_capability_map(cap_map)

        loaded = load_capability_map()
        assert loaded is not None
        assert loaded.entries[0].id == "test_cap"
        assert loaded.entries[0].problem_signals == ["foo"]

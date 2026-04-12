"""Tests for backend/config/ — loader, seller profile, and capability map."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from backend.config.loader import (
    SalesPlay,
    ProofPoint,
    SellerIntelligence,
    SellerProfileConfig,
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
        assert config.api_keys.llm_model == ""
        assert config.api_keys.llm_provider == ""
        assert config.api_keys.jsearch == ""
        assert config.api_keys.tavily == ""

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

    def test_round_trips_with_seller_intelligence_fields(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        entries = [
            CapabilityMapEntry({
                "id": "enriched",
                "label": "Enriched Cap",
                "problem_signals": ["signal"],
                "solution_areas": ["area"],
                "differentiators": ["Best in class"],
                "sales_plays": [{"play": "Scale play", "category": "infra"}],
                "proof_points": [{"customer": "Acme", "summary": "50% faster"}],
            })
        ]
        cap_map = CapabilityMap(entries=entries, version="1.0")
        save_capability_map(cap_map)

        loaded = load_capability_map()
        assert loaded is not None
        entry = loaded.entries[0]
        assert entry.differentiators == ["Best in class"]
        assert entry.sales_plays == [{"play": "Scale play", "category": "infra"}]
        assert entry.proof_points == [{"customer": "Acme", "summary": "50% faster"}]


class TestCapabilityMapEntrySellerIntelligenceDefaults:
    def test_new_fields_default_to_empty_lists(
        self, tmp_capability_map_path: Path, tmp_config_dir: Path
    ) -> None:
        """Existing maps without seller intelligence fields load without error."""
        tmp_capability_map_path.write_text(VALID_MAP_YAML, encoding="utf-8")
        cap_map = load_capability_map()
        assert cap_map is not None
        entry = cap_map.entries[0]
        assert entry.differentiators == []
        assert entry.sales_plays == []
        assert entry.proof_points == []

    def test_as_dict_includes_new_fields(self) -> None:
        entry = CapabilityMapEntry({
            "id": "test",
            "label": "Test",
            "differentiators": ["diff1"],
        })
        d = entry.as_dict()
        assert "differentiators" in d
        assert "sales_plays" in d
        assert "proof_points" in d
        assert d["differentiators"] == ["diff1"]
        assert d["sales_plays"] == []
        assert d["proof_points"] == []


# ---------------------------------------------------------------------------
# Seller intelligence model tests
# ---------------------------------------------------------------------------


class TestSellerIntelligenceModel:
    def test_default_empty(self) -> None:
        si = SellerIntelligence()
        assert si.differentiators == []
        assert si.sales_plays == []
        assert si.proof_points == []
        assert si.competitive_positioning == []
        assert si.last_scraped is None

    def test_full_model(self) -> None:
        si = SellerIntelligence(
            differentiators=["Best-in-class ML ops"],
            sales_plays=[SalesPlay(play="FinOps optimization", category="cost_optimization")],
            proof_points=[ProofPoint(customer="Acme Corp", summary="Reduced costs by 40%")],
            competitive_positioning=["Unlike X, we offer Y"],
            last_scraped="2026-04-12T00:00:00Z",
        )
        assert len(si.differentiators) == 1
        assert si.sales_plays[0].category == "cost_optimization"
        assert si.proof_points[0].customer == "Acme Corp"
        assert si.last_scraped == "2026-04-12T00:00:00Z"

    def test_serialization_round_trip(self) -> None:
        si = SellerIntelligence(
            differentiators=["Unique feature"],
            sales_plays=[SalesPlay(play="Cost reduction", category="cost")],
            proof_points=[ProofPoint(customer="TestCo", summary="50% improvement")],
            competitive_positioning=["Better than competitor"],
            last_scraped="2026-01-01T00:00:00Z",
        )
        data = si.model_dump()
        restored = SellerIntelligence.model_validate(data)
        assert restored.differentiators == si.differentiators
        assert restored.sales_plays[0].play == "Cost reduction"


class TestSellerProfileConfigWithIntelligence:
    def test_default_has_empty_intelligence(self) -> None:
        spc = SellerProfileConfig()
        assert spc.website_url is None
        assert isinstance(spc.seller_intelligence, SellerIntelligence)
        assert spc.seller_intelligence.differentiators == []

    def test_config_round_trip_with_intelligence(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.seller_profile.website_url = "https://example.com"
        config.seller_profile.seller_intelligence = SellerIntelligence(
            differentiators=["Fast deployment"],
            sales_plays=[SalesPlay(play="DevOps acceleration", category="devops")],
        )
        save_config(config)

        loaded = load_config()
        assert loaded.seller_profile.website_url == "https://example.com"
        assert loaded.seller_profile.seller_intelligence.differentiators == ["Fast deployment"]
        assert loaded.seller_profile.seller_intelligence.sales_plays[0].category == "devops"

    def test_backward_compat_old_config_without_intelligence(self, tmp_config_dir: Path) -> None:
        """Config files from before this feature (no website_url, no seller_intelligence) load fine."""
        config_file = tmp_config_dir / "config.json"
        old_config = {
            "seller_profile": {
                "company_name": "OldCo",
                "portfolio_summary": "Legacy tools",
                "portfolio_items": ["Tool A"],
            },
            "api_keys": {},
            "session_budget": {},
        }
        config_file.write_text(json.dumps(old_config), encoding="utf-8")

        config = load_config()
        assert config.seller_profile.company_name == "OldCo"
        assert config.seller_profile.website_url is None
        assert config.seller_profile.seller_intelligence.differentiators == []

    def test_update_seller_profile_with_intelligence(self, tmp_config_dir: Path) -> None:
        intelligence = SellerIntelligence(
            differentiators=["AI-native platform"],
            proof_points=[ProofPoint(customer="BigCorp", summary="2x productivity")],
        )
        profile = update_seller_profile(
            company_name="NewCo",
            portfolio_summary="AI tools",
            portfolio_items=["Agent SDK"],
            website_url="https://newco.com",
            seller_intelligence=intelligence,
        )
        assert profile.website_url == "https://newco.com"
        assert profile.seller_intelligence.differentiators == ["AI-native platform"]

        # Verify persistence
        reloaded = get_seller_profile()
        assert reloaded.website_url == "https://newco.com"
        assert reloaded.seller_intelligence.proof_points[0].customer == "BigCorp"

    def test_update_seller_profile_preserves_intelligence_when_not_provided(
        self, tmp_config_dir: Path
    ) -> None:
        """Updating profile without passing intelligence should preserve existing intelligence."""
        # Set initial intelligence
        update_seller_profile(
            company_name="Co",
            portfolio_summary="",
            portfolio_items=[],
            seller_intelligence=SellerIntelligence(differentiators=["Existing diff"]),
        )

        # Update only basic fields
        profile = update_seller_profile(
            company_name="Co Updated",
            portfolio_summary="Updated summary",
            portfolio_items=["New item"],
        )
        assert profile.company_name == "Co Updated"
        assert profile.seller_intelligence.differentiators == ["Existing diff"]


# ---------------------------------------------------------------------------
# Seller context fields tests
# ---------------------------------------------------------------------------


class TestSellerContextFields:
    def test_default_seller_context_fields(self, tmp_config_dir: Path) -> None:
        config = load_config()
        assert config.seller_profile.target_verticals == []
        assert config.seller_profile.value_metrics == []
        assert config.seller_profile.competitive_counters == {}
        assert config.seller_profile.company_size_messaging == {}

    def test_seller_context_round_trip(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.seller_profile.target_verticals = ["fintech", "healthcare"]
        config.seller_profile.value_metrics = ["40% faster deploys"]
        config.seller_profile.competitive_counters = {"Competitor": ["Lower cost"]}
        config.seller_profile.company_size_messaging = {"enterprise": "Scale message"}
        save_config(config)

        loaded = load_config()
        assert loaded.seller_profile.target_verticals == ["fintech", "healthcare"]
        assert loaded.seller_profile.value_metrics == ["40% faster deploys"]
        assert loaded.seller_profile.competitive_counters == {"Competitor": ["Lower cost"]}
        assert loaded.seller_profile.company_size_messaging == {"enterprise": "Scale message"}

    def test_backward_compat_without_context_fields(self, tmp_config_dir: Path) -> None:
        """Old configs without seller context fields load with empty defaults."""
        config_file = tmp_config_dir / "config.json"
        old_config = {
            "seller_profile": {
                "company_name": "OldCo",
                "portfolio_summary": "Tools",
                "portfolio_items": [],
            },
            "api_keys": {},
            "session_budget": {},
        }
        config_file.write_text(json.dumps(old_config), encoding="utf-8")
        config = load_config()
        assert config.seller_profile.target_verticals == []
        assert config.seller_profile.competitive_counters == {}

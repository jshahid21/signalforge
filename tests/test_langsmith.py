"""Tests for LangSmith tracing toggle (issues #31 and #32)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.config.loader import (
    LangSmithConfig,
    SignalForgeConfig,
    apply_langsmith_env,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------


class TestLangSmithConfig:
    def test_defaults(self) -> None:
        ls = LangSmithConfig()
        assert ls.enabled is False
        assert ls.api_key == ""
        assert ls.project == "signalforge"

    def test_config_includes_langsmith_defaults(self, tmp_config_dir: Path) -> None:
        config = load_config()
        assert isinstance(config.langsmith, LangSmithConfig)
        assert config.langsmith.enabled is False

    def test_round_trip(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.langsmith.enabled = True
        config.langsmith.api_key = "lsv2_pt_test1234"
        config.langsmith.project = "my-project"
        save_config(config)

        loaded = load_config()
        assert loaded.langsmith.enabled is True
        assert loaded.langsmith.api_key == "lsv2_pt_test1234"
        assert loaded.langsmith.project == "my-project"

    def test_backward_compat_old_config_without_langsmith(self, tmp_config_dir: Path) -> None:
        """Config files from before this feature (no langsmith key) load fine."""
        config_file = tmp_config_dir / "config.json"
        old_config = {
            "seller_profile": {"company_name": "OldCo"},
            "api_keys": {},
            "session_budget": {},
        }
        config_file.write_text(json.dumps(old_config), encoding="utf-8")
        config = load_config()
        assert config.langsmith.enabled is False
        assert config.langsmith.api_key == ""


# ---------------------------------------------------------------------------
# apply_langsmith_env tests
# ---------------------------------------------------------------------------


class TestApplyLangsmithEnv:
    def test_sets_env_when_enabled(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.langsmith.enabled = True
        config.langsmith.api_key = "lsv2_pt_abc123"
        config.langsmith.project = "test-proj"
        save_config(config)

        apply_langsmith_env(config)

        assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
        assert os.environ["LANGCHAIN_API_KEY"] == "lsv2_pt_abc123"
        assert os.environ["LANGCHAIN_PROJECT"] == "test-proj"

    def test_unsets_env_when_disabled(self, tmp_config_dir: Path) -> None:
        # First enable
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = "old-key"

        config = load_config()
        config.langsmith.enabled = False
        apply_langsmith_env(config)

        assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
        assert "LANGCHAIN_API_KEY" not in os.environ

    def test_disabled_when_no_api_key(self, tmp_config_dir: Path) -> None:
        config = load_config()
        config.langsmith.enabled = True
        config.langsmith.api_key = ""
        apply_langsmith_env(config)

        assert os.environ["LANGCHAIN_TRACING_V2"] == "false"


# ---------------------------------------------------------------------------
# Traceable decorator tests
# ---------------------------------------------------------------------------


class TestTraceableDecorator:
    async def test_noop_decorator_preserves_function(self) -> None:
        """The traceable decorator (no-op fallback) should not alter function behavior."""
        from backend.tracing import traceable

        @traceable(name="test_func")
        async def my_func(x: int) -> int:
            return x + 1

        result = await my_func(5)
        assert result == 6

    def test_noop_decorator_without_args(self) -> None:
        """The traceable decorator should work without keyword args."""
        from backend.tracing import traceable

        @traceable
        def my_sync_func(x: int) -> int:
            return x * 2

        assert my_sync_func(3) == 6


# ---------------------------------------------------------------------------
# Settings API tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_config_dir: Path):
    from fastapi.testclient import TestClient
    from backend.api.app import app
    return TestClient(app)


class TestLangSmithSettingsAPI:
    def test_get_langsmith_defaults(self, client) -> None:
        resp = client.get("/settings/langsmith")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["project"] == "signalforge"

    def test_put_and_get_langsmith(self, client) -> None:
        resp = client.put("/settings/langsmith", json={
            "enabled": True,
            "api_key": "lsv2_pt_testkey1234",
            "project": "my-project",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        resp = client.get("/settings/langsmith")
        data = resp.json()
        assert data["enabled"] is True
        assert data["project"] == "my-project"
        # API key should be masked
        assert data["api_key"].startswith("***")
        assert data["api_key"].endswith("1234")

    def test_put_masked_key_preserves_existing(self, client) -> None:
        """Sending a masked key (***...) should not overwrite the real key."""
        client.put("/settings/langsmith", json={
            "enabled": True,
            "api_key": "lsv2_pt_realkey5678",
            "project": "signalforge",
        })
        # Now send masked key
        client.put("/settings/langsmith", json={
            "enabled": True,
            "api_key": "***5678",
            "project": "signalforge",
        })
        # Verify real key is still stored
        config = load_config()
        assert config.langsmith.api_key == "lsv2_pt_realkey5678"

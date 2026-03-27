"""Shared pytest fixtures and configuration."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temporary config directory and redirect config reads/writes there."""
    monkeypatch.setenv("SIGNALFORGE_CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def tmp_capability_map_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temporary path for capability map files."""
    map_path = tmp_path / "capability_map.yaml"
    monkeypatch.setenv("SIGNALFORGE_CAPABILITY_MAP_PATH", str(map_path))
    return map_path

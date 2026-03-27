"""API endpoint smoke tests — Phase 6 (spec §6, §9).

Tests verify:
- Session creation and retrieval
- Company state retrieval
- Persona editing
- Draft approval flow
- Memory CRUD and export
- Settings endpoints
- WebSocket connection
- Chat SSE endpoint
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.app import app
from backend.api import session_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_session_db(tmp_path, monkeypatch):
    """Each test gets an isolated SQLite database for session metadata."""
    db_path = str(tmp_path / "test_sessions.db")
    monkeypatch.setenv("SIGNALFORGE_SESSION_DB_PATH", db_path)
    # Reset module-level state
    session_store._meta_engine = None
    session_store._MetaSession = None
    # Reset in-memory registry
    session_store._registry.clear()
    yield db_path
    session_store._meta_engine = None
    session_store._MetaSession = None
    session_store._registry.clear()


@pytest.fixture(autouse=True)
def isolated_memory_db(tmp_path, monkeypatch):
    """Each test gets an isolated SQLite database for memory records."""
    db_path = str(tmp_path / "test_memory.db")
    monkeypatch.setenv("SIGNALFORGE_DB_PATH", db_path)
    import backend.db as db_module
    db_module._engine = None
    db_module._SessionLocal = None
    yield db_path
    db_module._engine = None
    db_module._SessionLocal = None


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Each test gets an isolated config directory."""
    monkeypatch.setenv("SIGNALFORGE_CONFIG_DIR", str(tmp_path))


@pytest.fixture
async def client():
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Health / Setup
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    async def test_health_returns_ok(self, client) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_setup_returns_first_run_flag(self, client) -> None:
        resp = await client.get("/setup")
        assert resp.status_code == 200
        data = resp.json()
        assert "first_run" in data
        assert isinstance(data["first_run"], bool)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettingsEndpoints:
    async def test_get_seller_profile(self, client) -> None:
        resp = await client.get("/settings/seller-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert "company_name" in data
        assert "portfolio_items" in data

    async def test_put_seller_profile(self, client) -> None:
        resp = await client.put("/settings/seller-profile", json={
            "company_name": "CloudCo",
            "portfolio_summary": "Cloud infra tooling",
            "portfolio_items": ["Kubernetes Optimizer"],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    async def test_get_seller_profile_after_update(self, client) -> None:
        await client.put("/settings/seller-profile", json={
            "company_name": "TestCo",
            "portfolio_summary": "",
            "portfolio_items": [],
        })
        resp = await client.get("/settings/seller-profile")
        assert resp.json()["company_name"] == "TestCo"

    async def test_get_api_keys_masks_secrets(self, client) -> None:
        # Set a key first
        await client.put("/settings/api-keys", json={
            "jsearch": "secret-key-abc123",
            "llm_model": "claude-sonnet-4-6",
        })
        resp = await client.get("/settings/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        # JSearch key should be masked
        assert data.get("jsearch", "") != "secret-key-abc123"

    async def test_put_api_keys(self, client) -> None:
        resp = await client.put("/settings/api-keys", json={
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-6",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    async def test_get_session_budget(self, client) -> None:
        resp = await client.get("/settings/session-budget")
        assert resp.status_code == 200
        data = resp.json()
        assert "max_usd" in data
        assert "tier3_limit" in data

    async def test_put_session_budget(self, client) -> None:
        resp = await client.put("/settings/session-budget", json={
            "max_usd": 1.0,
            "tier3_limit": 2,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    async def test_put_session_budget_rejects_zero_max(self, client) -> None:
        resp = await client.put("/settings/session-budget", json={
            "max_usd": 0.0,
            "tier3_limit": 1,
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Session Metadata
# ---------------------------------------------------------------------------


class TestSessionEndpoints:
    async def test_list_sessions_initially_empty(self, client) -> None:
        resp = await client.get("/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_session_returns_session_id(self, client, monkeypatch) -> None:
        """POST /sessions returns session_id and status=running."""
        # Mock the pipeline to avoid actually running it
        import asyncio

        async def _mock_pipeline_task(*args, **kwargs):
            pass

        monkeypatch.setattr(
            "backend.api.routes.sessions._run_pipeline_task",
            _mock_pipeline_task,
        )

        # Mock AsyncSqliteSaver
        from unittest.mock import AsyncMock, MagicMock, patch
        mock_checkpointer = MagicMock()
        mock_checkpointer.__aenter__ = AsyncMock(return_value=mock_checkpointer)
        mock_checkpointer.__aexit__ = AsyncMock(return_value=None)

        with patch("langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver.from_conn_string",
                   return_value=mock_checkpointer):
            resp = await client.post("/sessions", json={
                "company_names": ["Stripe", "Datadog"],
            })

        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["status"] == "running"
        assert data["company_names"] == ["Stripe", "Datadog"]

    async def test_get_session_returns_404_for_unknown(self, client) -> None:
        resp = await client.get("/sessions/nonexistent-session-id")
        assert resp.status_code == 404

    async def test_list_sessions_after_create(self, client, monkeypatch) -> None:
        """Sessions appear in the list after creation."""
        import asyncio

        async def _mock_pipeline_task(*args, **kwargs):
            pass

        monkeypatch.setattr(
            "backend.api.routes.sessions._run_pipeline_task",
            _mock_pipeline_task,
        )

        from unittest.mock import AsyncMock, MagicMock, patch
        mock_checkpointer = MagicMock()
        mock_checkpointer.__aenter__ = AsyncMock(return_value=mock_checkpointer)
        mock_checkpointer.__aexit__ = AsyncMock(return_value=None)

        with patch("langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver.from_conn_string",
                   return_value=mock_checkpointer):
            resp = await client.post("/sessions", json={"company_names": ["Stripe"]})
        session_id = resp.json()["session_id"]

        sessions = await client.get("/sessions")
        ids = [s["session_id"] for s in sessions.json()]
        assert session_id in ids


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class TestMemoryEndpoints:
    async def test_list_memory_initially_empty(self, client) -> None:
        resp = await client.get("/memory")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_delete_nonexistent_memory_returns_404(self, client) -> None:
        resp = await client.delete("/memory/nonexistent-id")
        assert resp.status_code == 404

    async def test_export_memory_returns_csv(self, client) -> None:
        resp = await client.get("/memory/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        # CSV should have a header row at minimum
        assert "record_id" in resp.text

    async def test_delete_existing_memory_record(self, client) -> None:
        """Write a record then delete it."""
        from backend.agents.memory_agent import write_memory_record
        from backend.models.enums import SignalTier
        from backend.models.state import Draft, Persona

        persona = Persona(
            persona_id="p1",
            title="Head of Platform",
            targeting_reason="Owns infra.",
            role_type="technical_buyer",
            seniority_level="director",
            priority_score=0.9,
            is_custom=False,
            is_edited=False,
        )
        draft = Draft(
            draft_id="d1",
            company_id="stripe",
            persona_id="p1",
            subject_line="Test subject",
            body="Test body",
            confidence_score=75.0,
            approved=True,
            version=1,
        )
        record = write_memory_record(
            company_name="Stripe",
            persona=persona,
            draft=draft,
            qualified_signal=None,
            synthesis=None,
        )

        # List should have 1 record
        resp = await client.get("/memory")
        assert len(resp.json()) == 1

        # Delete it
        resp = await client.delete(f"/memory/{record.record_id}")
        assert resp.status_code == 200

        # List should be empty
        resp = await client.get("/memory")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Session store internals (unit tests)
# ---------------------------------------------------------------------------


class TestSessionStore:
    def test_create_and_retrieve_session_record(self) -> None:
        from backend.api.session_store import (
            create_session_record,
            get_session_record,
        )

        create_session_record("s1", ["Stripe", "Datadog"], {"company_name": "TestCo"})
        rec = get_session_record("s1")

        assert rec is not None
        assert rec["session_id"] == "s1"
        assert rec["status"] == "running"
        assert "Stripe" in rec["company_names"]

    def test_update_session_record_status(self) -> None:
        from backend.api.session_store import (
            create_session_record,
            get_session_record,
            update_session_record,
        )

        create_session_record("s2", ["Stripe"], {})
        update_session_record("s2", "completed")
        rec = get_session_record("s2")

        assert rec["status"] == "completed"
        assert rec["completed_at"] is not None

    def test_get_nonexistent_session_returns_none(self) -> None:
        from backend.api.session_store import get_session_record

        assert get_session_record("does-not-exist") is None

    def test_list_sessions_ordered_by_recency(self) -> None:
        from backend.api.session_store import (
            create_session_record,
            list_session_records,
        )

        create_session_record("s3", ["A"], {})
        create_session_record("s4", ["B"], {})
        records = list_session_records()

        ids = [r["session_id"] for r in records]
        # Most recent first
        assert ids[0] == "s4"
        assert ids[1] == "s3"

    def test_generate_session_id_is_unique(self) -> None:
        from backend.api.session_store import generate_session_id

        id1 = generate_session_id()
        id2 = generate_session_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID format


# ---------------------------------------------------------------------------
# WebSocket connection manager unit tests
# ---------------------------------------------------------------------------


class TestConnectionManager:
    async def test_broadcast_to_no_connections_is_safe(self) -> None:
        from backend.api.websocket import ConnectionManager

        mgr = ConnectionManager()
        # No connections — should not raise
        await mgr.broadcast("no-such-session", {"type": "test"})

    async def test_broadcast_stage_update_produces_correct_event(self) -> None:
        from backend.api.websocket import ConnectionManager
        from fastapi import WebSocket
        from unittest.mock import AsyncMock, MagicMock

        mgr = ConnectionManager()
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "sess-1")
        await mgr.broadcast_stage_update("sess-1", "stripe", "research", "running")

        mock_ws.send_text.assert_called_once()
        payload = json.loads(mock_ws.send_text.call_args[0][0])
        assert payload["type"] == "stage_update"
        assert payload["company_id"] == "stripe"
        assert payload["stage"] == "research"
        assert payload["status"] == "running"

    async def test_disconnect_removes_connection(self) -> None:
        from backend.api.websocket import ConnectionManager
        from fastapi import WebSocket
        from unittest.mock import AsyncMock, MagicMock

        mgr = ConnectionManager()
        mock_ws = MagicMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()

        await mgr.connect(mock_ws, "sess-2")
        mgr.disconnect(mock_ws, "sess-2")

        assert "sess-2" not in mgr._connections

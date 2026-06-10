from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.gateway.api import create_api
from tars.gateway.server import GatewayServer


@pytest.fixture
async def api_server(tmp_path: Path) -> GatewayServer:
    data_dir = tmp_path / ".tars"
    data_dir.mkdir()
    config = TarsConfig(data_dir=data_dir)
    db = Database(config.db_path)
    await db.connect()
    migrations_dir = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"
    await db.run_migrations(migrations_dir)
    server = GatewayServer(config, db)
    yield server  # type: ignore[misc]
    await db.close()


@pytest.fixture
def client(api_server: GatewayServer) -> TestClient:
    app = create_api(api_server)
    return TestClient(app)


def test_status_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_sessions"] == 0
    assert data["kill_switch"] is False
    assert "budget" in data


def test_create_session(client: TestClient) -> None:
    resp = client.post("/api/v1/sessions", json={"channel": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["channel"] == "test"


def test_get_session(client: TestClient) -> None:
    create_resp = client.post("/api/v1/sessions", json={"channel": "test"})
    sid = create_resp.json()["session_id"]

    resp = client.get(f"/api/v1/sessions/{sid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sid
    assert data["status"] == "idle"


def test_get_session_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/sessions/nonexistent")
    assert resp.status_code == 404


def test_list_lessons_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/brain/lessons")
    assert resp.status_code == 200
    assert resp.json() == []


def test_teach_lesson(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/brain/teach",
        json={"statement": "always test before deploy"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["statement"] == "always test before deploy"
    assert data["status"] == "CANDIDATE"
    assert data["confidence"] > 0


def test_teach_then_list(client: TestClient) -> None:
    client.post(
        "/api/v1/brain/teach",
        json={"statement": "lint before commit"},
    )
    resp = client.get("/api/v1/brain/lessons")
    assert resp.status_code == 200
    lessons = resp.json()
    assert len(lessons) == 1
    assert lessons[0]["statement"] == "lint before commit"


def test_grant_permission(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/permissions",
        json={"capability": "tool.shell", "scope": "/tmp"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["capability"] == "tool.shell"
    assert data["scope"] == "/tmp"


def test_budget_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert "spent_inr" in data
    assert "limit_inr" in data


def test_kill_switch(client: TestClient) -> None:
    resp = client.post("/api/v1/kill", json={"reason": "test kill"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reason"] == "test kill"

    status = client.get("/api/v1/status").json()
    assert status["kill_switch"] is True


def test_json_rpc_backward_compat(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/rpc",
        json={"method": "get_status", "params": {}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data


def test_sse_session_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/sse/nonexistent")
    assert resp.status_code == 404

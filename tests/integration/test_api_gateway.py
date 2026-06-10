from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.core.events import Event, EventType
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


def test_full_session_lifecycle(client: TestClient) -> None:
    create_resp = client.post("/api/v1/sessions", json={"channel": "integration"})
    assert create_resp.status_code == 200
    sid = create_resp.json()["session_id"]

    status_resp = client.get(f"/api/v1/sessions/{sid}")
    assert status_resp.json()["status"] == "idle"

    global_status = client.get("/api/v1/status").json()
    assert global_status["active_sessions"] >= 1


def test_teach_creates_retrievable_lesson(client: TestClient) -> None:
    teach_resp = client.post(
        "/api/v1/brain/teach",
        json={"statement": "integration test rule", "domain": "testing"},
    )
    hid = teach_resp.json()["heuristic_id"]

    lessons = client.get("/api/v1/brain/lessons").json()
    ids = [lesson["id"] for lesson in lessons]
    assert hid in ids


def test_kill_prevents_task_submission(client: TestClient) -> None:
    client.post("/api/v1/kill", json={"reason": "integration test"})

    create_resp = client.post("/api/v1/sessions", json={})
    sid = create_resp.json()["session_id"]

    task_resp = client.post(
        "/api/v1/tasks",
        json={"session_id": sid, "goal": "should fail"},
    )
    assert task_resp.status_code == 503


def test_websocket_receives_events(api_server: GatewayServer) -> None:
    import concurrent.futures

    app = create_api(api_server)
    client = TestClient(app)

    session = api_server.session_manager.create(channel="ws-test")

    received = None
    try:
        with client.websocket_connect(f"/api/v1/ws/{session.id}") as ws:
            api_server.event_bus.emit_nowait(
                Event(
                    type=EventType.TASK_STARTED,
                    data={"goal": "ws test"},
                    session_id=session.id,
                )
            )
            received = ws.receive_json()
    except concurrent.futures.CancelledError:
        pass

    assert received is not None
    assert received["type"] == EventType.TASK_STARTED.value
    assert received["data"]["goal"] == "ws test"
    assert received["session_id"] == session.id


def test_websocket_rejects_invalid_session(api_server: GatewayServer) -> None:
    app = create_api(api_server)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/v1/ws/nonexistent"):
        pass


def test_rpc_and_rest_agree_on_status(client: TestClient) -> None:
    rest_status = client.get("/api/v1/status").json()
    rpc_resp = client.post(
        "/api/v1/rpc",
        json={"method": "get_status", "params": {}},
    )
    rpc_status = rpc_resp.json()["result"]

    assert rest_status["kill_switch"] == rpc_status["kill_switch"]
    assert rest_status["active_sessions"] == rpc_status["active_sessions"]

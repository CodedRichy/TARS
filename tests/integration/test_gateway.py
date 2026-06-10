from __future__ import annotations

from pathlib import Path

import pytest

from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.gateway.server import GatewayServer
from tars.gateway.session import SessionStatus
from tars.genome.models import Outcome

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def gw_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def config(tmp_path: Path) -> TarsConfig:
    return TarsConfig(data_dir=tmp_path)


@pytest.fixture
def server(config: TarsConfig, gw_db: Database) -> GatewayServer:
    return GatewayServer(config, gw_db)


@pytest.mark.asyncio
async def test_create_session(server: GatewayServer) -> None:
    session = server.session_manager.create(channel="cli")
    assert session.status == SessionStatus.IDLE
    assert session.channel == "cli"


@pytest.mark.asyncio
async def test_kill_switch(server: GatewayServer) -> None:
    server.session_manager.create()
    await server.permissions.grant("tool.shell")

    result = await server.kill_switch.trigger("test kill")
    assert result["killed_sessions"] == 1
    assert result["revoked_permissions"] == 1
    assert server.kill_switch.is_triggered


@pytest.mark.asyncio
async def test_submit_task_after_kill(server: GatewayServer) -> None:
    await server.kill_switch.trigger("test")
    session = server.session_manager.create()

    result = await server.submit_task(session, goal="echo test")
    assert result.outcome == Outcome.ABORTED


@pytest.mark.asyncio
async def test_rpc_get_status(server: GatewayServer) -> None:
    server.session_manager.create()
    resp = await server.handle_rpc({"method": "get_status"})
    assert "result" in resp
    assert resp["result"]["active_sessions"] == 1


@pytest.mark.asyncio
async def test_rpc_grant_permission(server: GatewayServer) -> None:
    resp = await server.handle_rpc(
        {
            "method": "grant_permission",
            "params": {"capability": "tool.shell", "scope": "/tmp"},
        }
    )
    assert "result" in resp
    assert resp["result"]["capability"] == "tool.shell"


@pytest.mark.asyncio
async def test_rpc_kill(server: GatewayServer) -> None:
    server.session_manager.create()
    resp = await server.handle_rpc(
        {
            "method": "kill",
            "params": {"reason": "test"},
        }
    )
    assert resp["result"]["reason"] == "test"
    assert server.kill_switch.is_triggered


@pytest.mark.asyncio
async def test_rpc_unknown_method(server: GatewayServer) -> None:
    resp = await server.handle_rpc({"method": "nonexistent"})
    assert "error" in resp


@pytest.mark.asyncio
async def test_kill_switch_reset(server: GatewayServer) -> None:
    await server.kill_switch.trigger("test")
    assert server.kill_switch.is_triggered
    server.kill_switch.reset()
    assert not server.kill_switch.is_triggered

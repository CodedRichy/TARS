from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tars.agent.permissions import (
    Permission,
    PermissionDeniedError,
    PermissionManager,
)
from tars.core.db import Database

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def perm_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def perms(perm_db: Database) -> PermissionManager:
    return PermissionManager(perm_db)


@pytest.mark.asyncio
async def test_deny_by_default(perms: PermissionManager) -> None:
    assert not await perms.check("tool.shell")


@pytest.mark.asyncio
async def test_grant_and_check(perms: PermissionManager) -> None:
    await perms.grant("tool.shell")
    assert await perms.check("tool.shell")


@pytest.mark.asyncio
async def test_wildcard_scope(perms: PermissionManager) -> None:
    await perms.grant("tool.shell", scope="*")
    assert await perms.check("tool.shell", scope="/tmp")


@pytest.mark.asyncio
async def test_scoped_permission(perms: PermissionManager) -> None:
    await perms.grant("tool.shell", scope="/tmp")
    assert await perms.check("tool.shell", scope="/tmp")
    assert not await perms.check("tool.shell", scope="/etc")


@pytest.mark.asyncio
async def test_revoke(perms: PermissionManager) -> None:
    await perms.grant("tool.shell")
    assert await perms.check("tool.shell")
    count = await perms.revoke("tool.shell")
    assert count == 1
    assert not await perms.check("tool.shell")


@pytest.mark.asyncio
async def test_revoke_all(perms: PermissionManager) -> None:
    await perms.grant("tool.shell")
    await perms.grant("tool.read_file")
    count = await perms.revoke_all()
    assert count == 2
    assert not await perms.check("tool.shell")
    assert not await perms.check("tool.read_file")


@pytest.mark.asyncio
async def test_expired_permission(perms: PermissionManager) -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    await perms.grant("tool.shell", expires_at=past)
    assert not await perms.check("tool.shell")


@pytest.mark.asyncio
async def test_require_raises(perms: PermissionManager) -> None:
    with pytest.raises(PermissionDeniedError, match="tool.shell"):
        await perms.require("tool.shell")


@pytest.mark.asyncio
async def test_list_active(perms: PermissionManager) -> None:
    await perms.grant("tool.shell")
    await perms.grant("tool.read_file")
    active = await perms.list_active()
    assert len(active) == 2


def test_permission_model_active() -> None:
    p = Permission(capability="test", scope="*")
    assert p.is_active


def test_permission_model_revoked() -> None:
    p = Permission(capability="test", revoked_at=datetime.now(UTC))
    assert not p.is_active


def test_permission_model_expired() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    p = Permission(capability="test", expires_at=past)
    assert not p.is_active

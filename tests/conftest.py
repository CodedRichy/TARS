from __future__ import annotations

from pathlib import Path

import pytest

from tars.core.config import DEFAULT_CONFIG_TOML, TarsConfig, load_config
from tars.core.db import Database


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / ".tars"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def tmp_config(tmp_data_dir: Path) -> TarsConfig:
    config_path = tmp_data_dir / "config.toml"
    config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return load_config(tmp_data_dir)


@pytest.fixture
async def tmp_db(tmp_data_dir: Path) -> Database:
    db = Database(tmp_data_dir / "tars.db")
    await db.connect()
    migrations_dir = Path(__file__).parent.parent / "src" / "tars" / "migrations"
    await db.run_migrations(migrations_dir)
    yield db  # type: ignore[misc]
    await db.close()

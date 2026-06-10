from __future__ import annotations

import os
from pathlib import Path

from tars.core.config import DEFAULT_CONFIG_TOML, TarsConfig, load_config


def test_default_config() -> None:
    cfg = TarsConfig()
    assert cfg.models.local_provider == "ollama"
    assert cfg.models.cheap_provider == "openai"
    assert cfg.models.frontier_provider == "anthropic"
    assert cfg.budget.daily_limit_inr == 50.0
    assert cfg.telegram.enabled is False
    assert cfg.db_path.name == "tars.db"


def test_load_config_no_file(tmp_path: Path) -> None:
    data_dir = tmp_path / ".tars"
    data_dir.mkdir()
    cfg = load_config(data_dir)
    assert cfg.data_dir == data_dir
    assert cfg.models.local_model == "llama3.2:3b"


def test_load_config_from_toml(tmp_path: Path) -> None:
    data_dir = tmp_path / ".tars"
    data_dir.mkdir()
    config_path = data_dir / "config.toml"
    config_path.write_text(
        DEFAULT_CONFIG_TOML.replace("daily_limit_inr = 50", "daily_limit_inr = 100"),
        encoding="utf-8",
    )
    cfg = load_config(data_dir)
    assert cfg.budget.daily_limit_inr == 100.0


def test_env_override_telegram_token(tmp_path: Path, monkeypatch: object) -> None:
    data_dir = tmp_path / ".tars"
    data_dir.mkdir()
    config_path = data_dir / "config.toml"
    config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")

    os.environ["TARS_TELEGRAM_TOKEN"] = "test-token-123"
    try:
        cfg = load_config(data_dir)
        assert cfg.telegram.bot_token == "test-token-123"
    finally:
        del os.environ["TARS_TELEGRAM_TOKEN"]


def test_config_paths(tmp_path: Path) -> None:
    cfg = TarsConfig(data_dir=tmp_path)
    assert cfg.db_path == tmp_path / "tars.db"
    assert cfg.config_path == tmp_path / "config.toml"
    assert cfg.migrations_dir.name == "migrations"

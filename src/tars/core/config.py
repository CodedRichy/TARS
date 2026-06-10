from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def default_data_dir() -> Path:
    return Path(os.environ.get("TARS_DATA_DIR", "~/.tars")).expanduser()


class ModelsConfig(BaseModel):
    local_provider: str = "ollama"
    local_model: str = "llama3.2:3b"
    cheap_provider: str = "openai"
    cheap_model: str = "gpt-4.1-mini"
    frontier_provider: str = "anthropic"
    frontier_model: str = "claude-sonnet-4-20250514"


class BudgetConfig(BaseModel):
    daily_limit_inr: float = 50.0
    warn_threshold_inr: float = 40.0


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = Field(default="")


class DoormanConfig(BaseModel):
    cron_triggers: list[str] = Field(default_factory=list)
    file_watch_paths: list[str] = Field(default_factory=list)
    imap_enabled: bool = False


class MCPServerEntry(BaseModel):
    transport: str = "stdio"
    command: list[str] = Field(default_factory=list)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    servers: dict[str, MCPServerEntry] = Field(default_factory=dict)


class TarsConfig(BaseModel):
    data_dir: Path = Field(default_factory=default_data_dir)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    doorman: DoormanConfig = Field(default_factory=DoormanConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "tars.db"

    @property
    def config_path(self) -> Path:
        return self.data_dir / "config.toml"

    @property
    def migrations_dir(self) -> Path:
        return Path(__file__).parent.parent / "migrations"


def load_config(data_dir: Path | None = None) -> TarsConfig:
    data_dir = data_dir or default_data_dir()
    config_path = data_dir / "config.toml"

    if not config_path.exists():
        return TarsConfig(data_dir=data_dir)

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    flat: dict[str, Any] = {"data_dir": data_dir}
    if "models" in raw:
        flat["models"] = raw["models"]
    if "budget" in raw:
        flat["budget"] = raw["budget"]
    if "telegram" in raw:
        flat["telegram"] = raw["telegram"]
    if "doorman" in raw:
        flat["doorman"] = raw["doorman"]
    if "mcp" in raw:
        flat["mcp"] = raw["mcp"]
    if "mcp_servers" in raw:
        flat["mcp"] = {"servers": raw["mcp_servers"]}

    env_token = os.environ.get("TARS_TELEGRAM_TOKEN")
    if env_token:
        tg = flat.get("telegram", {})
        if isinstance(tg, dict):
            tg["bot_token"] = env_token
            flat["telegram"] = tg

    return TarsConfig(**flat)


DEFAULT_CONFIG_TOML = """\
[models]
local_provider = "ollama"
local_model = "llama3.2:3b"
cheap_provider = "openai"
cheap_model = "gpt-4.1-mini"
frontier_provider = "anthropic"
frontier_model = "claude-sonnet-4-20250514"

[budget]
daily_limit_inr = 50
warn_threshold_inr = 40

[telegram]
enabled = false
bot_token = ""

[doorman]
cron_triggers = []
file_watch_paths = []
imap_enabled = false

# [mcp_servers.filesystem]
# transport = "stdio"
# command = ["npx", "-y", "@modelcontextprotocol/server-filesystem"]
# args = ["/home/user/projects"]
#
# [mcp_servers.github]
# transport = "stdio"
# command = ["npx", "-y", "@modelcontextprotocol/server-github"]
# env = {GITHUB_PERSONAL_ACCESS_TOKEN = ""}
"""

from __future__ import annotations

from tars.core.config import DEFAULT_CONFIG_TOML, TarsConfig, load_config
from tars.core.db import Database
from tars.doctor.checks import CheckResult


class DoctorFixer:
    def __init__(self, config: TarsConfig | None = None) -> None:
        self.config = config or load_config()

    async def fix(self, check: CheckResult) -> str | None:
        if not check.fixable:
            return None

        fixers = {
            "data_dir": self._fix_data_dir,
            "config_file": self._fix_config_file,
            "database": self._fix_database,
            "migrations": self._fix_migrations,
            "dependencies": self._fix_dependencies,
        }

        fixer = fixers.get(check.name)
        if fixer:
            return await fixer()
        return None

    async def _fix_data_dir(self) -> str:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        return f"Created {self.config.data_dir}"

    async def _fix_config_file(self) -> str:
        self.config.config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
        return f"Created default config at {self.config.config_path}"

    async def _fix_database(self) -> str:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        db = Database(self.config.db_path)
        await db.connect()
        await db.run_migrations(self.config.migrations_dir)
        await db.close()
        return f"Created database at {self.config.db_path}"

    async def _fix_migrations(self) -> str:
        db = Database(self.config.db_path)
        await db.connect()
        count = await db.run_migrations(self.config.migrations_dir)
        await db.close()
        return f"Applied {count} pending migration(s)"

    async def _fix_dependencies(self) -> str:
        return "Run: pip install -e '.[dev]' to install missing dependencies"

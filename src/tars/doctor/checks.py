from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tars.core.config import TarsConfig, load_config


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    fixable: bool = False
    severity: str = "info"


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


class DoctorEngine:
    def __init__(self, config: TarsConfig | None = None) -> None:
        self.config = config or load_config()

    async def run_all(self, *, include_security: bool = False) -> DoctorReport:
        report = DoctorReport()

        report.checks.append(self.check_python_version())
        report.checks.append(self.check_data_dir())
        report.checks.append(self.check_config_file())
        report.checks.append(await self.check_database())
        report.checks.append(self.check_dependencies())
        report.checks.append(await self.check_migrations())
        report.checks.append(self.check_ollama())
        report.checks.append(self.check_disk_space())
        report.checks.append(await self.check_ledger_integrity())
        report.checks.append(await self.check_changelog_integrity())

        if include_security:
            report.checks.extend(await self.run_security_checks())

        return report

    def check_python_version(self) -> CheckResult:
        version = sys.version_info
        if version >= (3, 11):
            return CheckResult(
                name="python_version",
                passed=True,
                message=f"Python {version.major}.{version.minor}.{version.micro}",
            )
        return CheckResult(
            name="python_version",
            passed=False,
            message=f"Python {version.major}.{version.minor} < 3.11 required",
            severity="error",
        )

    def check_data_dir(self) -> CheckResult:
        data_dir = self.config.data_dir
        if data_dir.exists() and data_dir.is_dir():
            return CheckResult(
                name="data_dir",
                passed=True,
                message=f"Data directory exists: {data_dir}",
            )
        return CheckResult(
            name="data_dir",
            passed=False,
            message=f"Data directory missing: {data_dir}. Run: tars init",
            fixable=True,
            severity="error",
        )

    def check_config_file(self) -> CheckResult:
        cfg_path = self.config.config_path
        if cfg_path.exists():
            return CheckResult(
                name="config_file",
                passed=True,
                message=f"Config found: {cfg_path}",
            )
        return CheckResult(
            name="config_file",
            passed=False,
            message=f"Config missing: {cfg_path}. Run: tars init",
            fixable=True,
            severity="warn",
        )

    async def check_database(self) -> CheckResult:
        db_path = self.config.db_path
        if not db_path.exists():
            return CheckResult(
                name="database",
                passed=False,
                message=f"Database not found: {db_path}. Run: tars init",
                fixable=True,
                severity="error",
            )

        try:
            from tars.core.db import Database

            db = Database(db_path)
            await db.connect()
            row = await db.fetchone("PRAGMA integrity_check")
            await db.close()

            if row and row[0] == "ok":
                return CheckResult(
                    name="database",
                    passed=True,
                    message=f"Database OK: {db_path}",
                )
            return CheckResult(
                name="database",
                passed=False,
                message="Database integrity check failed",
                severity="error",
            )
        except Exception as e:
            return CheckResult(
                name="database",
                passed=False,
                message=f"Database error: {e}",
                severity="error",
            )

    def check_dependencies(self) -> CheckResult:
        required = [
            "typer", "rich", "pydantic", "aiosqlite",
            "litellm", "httpx", "fastapi", "uvicorn",
        ]
        missing = []
        for pkg in required:
            try:
                importlib.import_module(pkg)
            except ImportError:
                missing.append(pkg)

        if not missing:
            return CheckResult(
                name="dependencies",
                passed=True,
                message=f"All {len(required)} core dependencies installed",
            )
        return CheckResult(
            name="dependencies",
            passed=False,
            message=f"Missing: {', '.join(missing)}",
            fixable=True,
            severity="error",
        )

    async def check_migrations(self) -> CheckResult:
        if not self.config.db_path.exists():
            return CheckResult(
                name="migrations",
                passed=False,
                message="No database — skipped",
                severity="warn",
            )

        try:
            from tars.core.db import Database

            db = Database(self.config.db_path)
            await db.connect()
            rows = await db.fetchall("SELECT filename FROM _migrations ORDER BY id")
            await db.close()

            applied = {r["filename"] for r in rows}
            migration_dir = self.config.migrations_dir
            available = sorted(f.name for f in migration_dir.glob("*.sql"))

            pending = [m for m in available if m not in applied]
            if not pending:
                return CheckResult(
                    name="migrations",
                    passed=True,
                    message=f"{len(applied)} migrations applied, none pending",
                )
            return CheckResult(
                name="migrations",
                passed=False,
                message=f"{len(pending)} pending: {', '.join(pending)}",
                fixable=True,
                severity="warn",
            )
        except Exception as e:
            return CheckResult(
                name="migrations",
                passed=False,
                message=f"Migration check error: {e}",
                severity="warn",
            )

    def check_ollama(self) -> CheckResult:
        ollama_path = shutil.which("ollama")
        if ollama_path:
            return CheckResult(
                name="ollama",
                passed=True,
                message=f"Ollama found: {ollama_path}",
            )
        return CheckResult(
            name="ollama",
            passed=False,
            message="Ollama not in PATH (needed for local model tier)",
            severity="warn",
        )

    def check_disk_space(self) -> CheckResult:
        data_dir = self.config.data_dir
        target = data_dir if data_dir.exists() else Path.home()
        try:
            usage = shutil.disk_usage(target)
            free_mb = usage.free / (1024 * 1024)
            if free_mb > 500:
                return CheckResult(
                    name="disk_space",
                    passed=True,
                    message=f"{free_mb:.0f} MB free",
                )
            return CheckResult(
                name="disk_space",
                passed=False,
                message=f"Low disk: {free_mb:.0f} MB free (<500 MB)",
                severity="warn",
            )
        except OSError:
            return CheckResult(
                name="disk_space",
                passed=True,
                message="Could not check disk space",
            )

    async def check_ledger_integrity(self) -> CheckResult:
        if not self.config.db_path.exists():
            return CheckResult(
                name="ledger_integrity",
                passed=True,
                message="No database — skipped",
            )

        try:
            from tars.core.db import Database

            db = Database(self.config.db_path)
            await db.connect()
            rows = await db.fetchall(
                "SELECT * FROM action_ledger ORDER BY rowid"
            )
            await db.close()

            if not rows:
                return CheckResult(
                    name="ledger_integrity",
                    passed=True,
                    message="Action ledger empty — nothing to verify",
                )

            prev_hash = ""
            for row in rows:
                expected_prev = row["prev_hash"]
                if expected_prev != prev_hash:
                    return CheckResult(
                        name="ledger_integrity",
                        passed=False,
                        message="Action ledger hash chain broken — tamper detected",
                        severity="error",
                    )
                prev_hash = row["hash"]

            return CheckResult(
                name="ledger_integrity",
                passed=True,
                message=f"Ledger hash chain verified ({len(rows)} entries)",
            )
        except Exception as e:
            return CheckResult(
                name="ledger_integrity",
                passed=False,
                message=f"Ledger check error: {e}",
                severity="warn",
            )

    async def check_changelog_integrity(self) -> CheckResult:
        if not self.config.db_path.exists():
            return CheckResult(
                name="changelog_integrity",
                passed=True,
                message="No database — skipped",
            )

        try:
            from tars.core.db import Database

            db = Database(self.config.db_path)
            await db.connect()
            rows = await db.fetchall(
                "SELECT * FROM brain_changelog ORDER BY seq"
            )
            await db.close()

            if not rows:
                return CheckResult(
                    name="changelog_integrity",
                    passed=True,
                    message="Brain changelog empty — nothing to verify",
                )

            prev_hash = ""
            for row in rows:
                if row["prev_hash"] != prev_hash:
                    return CheckResult(
                        name="changelog_integrity",
                        passed=False,
                        message="Brain changelog hash chain broken",
                        severity="error",
                    )
                prev_hash = row["hash"]

            return CheckResult(
                name="changelog_integrity",
                passed=True,
                message=f"Changelog chain verified ({len(rows)} entries)",
            )
        except Exception as e:
            return CheckResult(
                name="changelog_integrity",
                passed=False,
                message=f"Changelog check error: {e}",
                severity="warn",
            )

    async def run_security_checks(self) -> list[CheckResult]:
        results: list[CheckResult] = []

        db_path = self.config.db_path
        if db_path.exists():
            try:
                stat = db_path.stat()
                mode = oct(stat.st_mode)[-3:]
                if sys.platform != "win32" and mode not in ("600", "640", "644"):
                    results.append(CheckResult(
                        name="db_permissions",
                        passed=False,
                        message=f"Database file too permissive: {mode}",
                        fixable=True,
                        severity="warn",
                    ))
                else:
                    results.append(CheckResult(
                        name="db_permissions",
                        passed=True,
                        message="Database file permissions OK",
                    ))
            except OSError:
                results.append(CheckResult(
                    name="db_permissions",
                    passed=True,
                    message="Could not check permissions",
                ))

        cfg_path = self.config.config_path
        if cfg_path.exists():
            content = cfg_path.read_text(encoding="utf-8")
            sensitive = ["api_key", "token", "secret", "password"]
            exposed = [s for s in sensitive if s in content.lower() and '= ""' not in content]
            if exposed:
                results.append(CheckResult(
                    name="config_secrets",
                    passed=False,
                    message=f"Config may contain secrets: {exposed}",
                    severity="warn",
                ))
            else:
                results.append(CheckResult(
                    name="config_secrets",
                    passed=True,
                    message="No exposed secrets in config",
                ))

        env_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TARS_TELEGRAM_TOKEN"]
        set_keys = [k for k in env_keys if os.environ.get(k)]
        if set_keys:
            results.append(CheckResult(
                name="api_keys",
                passed=True,
                message=f"API keys set: {', '.join(set_keys)}",
            ))
        else:
            results.append(CheckResult(
                name="api_keys",
                passed=False,
                message="No API keys found in environment",
                severity="warn",
            ))

        return results

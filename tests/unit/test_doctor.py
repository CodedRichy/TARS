from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tars.core.config import DEFAULT_CONFIG_TOML, TarsConfig
from tars.doctor.checks import CheckResult, DoctorEngine, DoctorReport
from tars.doctor.fixes import DoctorFixer


@pytest.fixture
def doctor_config(tmp_data_dir: Path) -> TarsConfig:
    config_path = tmp_data_dir / "config.toml"
    config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return TarsConfig(data_dir=tmp_data_dir)


@pytest.fixture
def engine(doctor_config: TarsConfig) -> DoctorEngine:
    return DoctorEngine(doctor_config)


class TestCheckResult:
    def test_defaults(self) -> None:
        r = CheckResult(name="test", passed=True, message="ok")
        assert r.fixable is False
        assert r.severity == "info"

    def test_failed_with_severity(self) -> None:
        r = CheckResult(name="x", passed=False, message="bad", severity="error")
        assert not r.passed
        assert r.severity == "error"


class TestDoctorReport:
    def test_empty_report(self) -> None:
        report = DoctorReport()
        assert report.passed == 0
        assert report.failed == 0
        assert report.all_passed

    def test_mixed_results(self) -> None:
        report = DoctorReport(checks=[
            CheckResult(name="a", passed=True, message="ok"),
            CheckResult(name="b", passed=False, message="bad"),
            CheckResult(name="c", passed=True, message="ok"),
        ])
        assert report.passed == 2
        assert report.failed == 1
        assert not report.all_passed


class TestDoctorEngine:
    def test_python_version(self, engine: DoctorEngine) -> None:
        result = engine.check_python_version()
        assert result.name == "python_version"
        assert result.passed

    def test_data_dir_exists(self, engine: DoctorEngine) -> None:
        result = engine.check_data_dir()
        assert result.passed

    def test_data_dir_missing(self, tmp_path: Path) -> None:
        cfg = TarsConfig(data_dir=tmp_path / "nonexistent")
        engine = DoctorEngine(cfg)
        result = engine.check_data_dir()
        assert not result.passed
        assert result.fixable

    def test_config_file_exists(self, engine: DoctorEngine) -> None:
        result = engine.check_config_file()
        assert result.passed

    def test_config_file_missing(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "noconfig"
        data_dir.mkdir()
        cfg = TarsConfig(data_dir=data_dir)
        engine = DoctorEngine(cfg)
        result = engine.check_config_file()
        assert not result.passed
        assert result.fixable

    @pytest.mark.asyncio
    async def test_database_missing(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "nodb"
        data_dir.mkdir()
        cfg = TarsConfig(data_dir=data_dir)
        engine = DoctorEngine(cfg)
        result = await engine.check_database()
        assert not result.passed
        assert result.fixable

    @pytest.mark.asyncio
    async def test_database_ok(self, doctor_config: TarsConfig) -> None:
        from tars.core.db import Database

        db = Database(doctor_config.db_path)
        await db.connect()
        await db.run_migrations(doctor_config.migrations_dir)
        await db.close()

        engine = DoctorEngine(doctor_config)
        result = await engine.check_database()
        assert result.passed

    def test_dependencies(self, engine: DoctorEngine) -> None:
        result = engine.check_dependencies()
        assert result.passed

    def test_ollama_check(self, engine: DoctorEngine) -> None:
        result = engine.check_ollama()
        assert result.name == "ollama"

    def test_disk_space(self, engine: DoctorEngine) -> None:
        result = engine.check_disk_space()
        assert result.passed

    @pytest.mark.asyncio
    async def test_ledger_no_db(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "noledger"
        data_dir.mkdir()
        cfg = TarsConfig(data_dir=data_dir)
        engine = DoctorEngine(cfg)
        result = await engine.check_ledger_integrity()
        assert result.passed

    @pytest.mark.asyncio
    async def test_changelog_no_db(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "nocl"
        data_dir.mkdir()
        cfg = TarsConfig(data_dir=data_dir)
        engine = DoctorEngine(cfg)
        result = await engine.check_changelog_integrity()
        assert result.passed

    @pytest.mark.asyncio
    async def test_run_all(self, doctor_config: TarsConfig) -> None:
        from tars.core.db import Database

        db = Database(doctor_config.db_path)
        await db.connect()
        await db.run_migrations(doctor_config.migrations_dir)
        await db.close()

        engine = DoctorEngine(doctor_config)
        report = await engine.run_all()
        assert len(report.checks) == 10

    @pytest.mark.asyncio
    async def test_run_all_with_security(self, doctor_config: TarsConfig) -> None:
        from tars.core.db import Database

        db = Database(doctor_config.db_path)
        await db.connect()
        await db.run_migrations(doctor_config.migrations_dir)
        await db.close()

        engine = DoctorEngine(doctor_config)
        report = await engine.run_all(include_security=True)
        assert len(report.checks) > 10

    @pytest.mark.asyncio
    async def test_migrations_check_with_db(self, doctor_config: TarsConfig) -> None:
        from tars.core.db import Database

        db = Database(doctor_config.db_path)
        await db.connect()
        await db.run_migrations(doctor_config.migrations_dir)
        await db.close()

        engine = DoctorEngine(doctor_config)
        result = await engine.check_migrations()
        assert result.passed

    @pytest.mark.asyncio
    async def test_security_api_keys(self, engine: DoctorEngine) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False):
            results = await engine.run_security_checks()
            api_check = [r for r in results if r.name == "api_keys"][0]
            assert api_check.passed


class TestDoctorFixer:
    @pytest.mark.asyncio
    async def test_fix_data_dir(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "fix_test"
        cfg = TarsConfig(data_dir=new_dir)
        fixer = DoctorFixer(cfg)
        check = CheckResult(name="data_dir", passed=False, message="missing", fixable=True)
        result = await fixer.fix(check)
        assert result is not None
        assert new_dir.exists()

    @pytest.mark.asyncio
    async def test_fix_config_file(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "fix_cfg"
        data_dir.mkdir()
        cfg = TarsConfig(data_dir=data_dir)
        fixer = DoctorFixer(cfg)
        check = CheckResult(name="config_file", passed=False, message="missing", fixable=True)
        result = await fixer.fix(check)
        assert result is not None
        assert cfg.config_path.exists()

    @pytest.mark.asyncio
    async def test_fix_unfixable(self, doctor_config: TarsConfig) -> None:
        fixer = DoctorFixer(doctor_config)
        check = CheckResult(name="python_version", passed=False, message="too old", fixable=False)
        result = await fixer.fix(check)
        assert result is None

    @pytest.mark.asyncio
    async def test_fix_dependencies_returns_instruction(self, doctor_config: TarsConfig) -> None:
        fixer = DoctorFixer(doctor_config)
        check = CheckResult(name="dependencies", passed=False, message="missing", fixable=True)
        result = await fixer.fix(check)
        assert result is not None
        assert "pip install" in result

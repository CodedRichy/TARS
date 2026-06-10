from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tars.core.db import Database
from tars.curves.digest import ImprovementDigest
from tars.curves.renderer import CurveRenderer, sparkline, trend_arrow
from tars.curves.snapshot import SnapshotCollector


@pytest.fixture
async def curves_db(tmp_data_dir: Path) -> Database:
    db = Database(tmp_data_dir / "tars.db")
    await db.connect()
    migrations_dir = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"
    await db.run_migrations(migrations_dir)
    yield db  # type: ignore[misc]
    await db.close()


class TestSparkline:
    def test_empty(self) -> None:
        assert sparkline([]) == ""

    def test_single_value(self) -> None:
        result = sparkline([0.5])
        assert len(result) == 1

    def test_ascending(self) -> None:
        result = sparkline([0.0, 0.5, 1.0], width=3)
        assert result[0] == "▁"
        assert result[-1] == "█"

    def test_constant(self) -> None:
        result = sparkline([0.5, 0.5, 0.5], width=3)
        assert len(result) == 3

    def test_width_cap(self) -> None:
        result = sparkline(list(range(100)), width=10)
        assert len(result) <= 10


class TestTrendArrow:
    def test_up(self) -> None:
        assert trend_arrow(0.05) == "↑"

    def test_down(self) -> None:
        assert trend_arrow(-0.05) == "↓"

    def test_flat(self) -> None:
        assert trend_arrow(0.005) == "→"

    def test_none(self) -> None:
        assert trend_arrow(None) == ""


class TestCurveRenderer:
    def _make_snapshots(self, n: int = 5) -> list[dict]:
        return [
            {
                "period_label": f"2026-06-{i+1:02d}",
                "success_rate": 0.4 + i * 0.1,
                "growth_score": 30 + i * 10,
                "total_episodes": 5 + i,
                "active_lessons": i,
                "avg_confidence": 0.5 + i * 0.05,
                "cost_per_task": 1.0 - i * 0.1,
                "total_lessons": 10,
                "delta_success_rate": 0.1 if i > 0 else None,
            }
            for i in range(n)
        ]

    def test_terminal_output(self) -> None:
        renderer = CurveRenderer(self._make_snapshots())
        output = renderer.to_terminal()
        assert "TARS" in output
        assert "Success Rate" in output
        assert "Growth Score" in output

    def test_terminal_empty(self) -> None:
        renderer = CurveRenderer([])
        assert "No improvement data" in renderer.to_terminal()

    def test_svg_output(self) -> None:
        renderer = CurveRenderer(self._make_snapshots())
        svg = renderer.to_svg()
        assert "<svg" in svg
        assert "TARS" in svg
        assert "#1a1b2e" in svg

    def test_badge_url(self) -> None:
        renderer = CurveRenderer(self._make_snapshots())
        url = renderer.to_badge()
        assert "shields.io" in url
        assert "TARS" in url

    def test_json_output(self) -> None:
        import json

        renderer = CurveRenderer(self._make_snapshots())
        data = json.loads(renderer.to_json())
        assert "snapshots" in data
        assert "latest" in data
        assert "sparkline_success" in data

    def test_save_svg(self, tmp_path: Path) -> None:
        renderer = CurveRenderer(self._make_snapshots())
        path = renderer.save_svg(tmp_path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "<svg" in content


class TestSnapshotCollector:
    @pytest.mark.asyncio
    async def test_collect_daily_empty(self, curves_db: Database) -> None:
        collector = SnapshotCollector(curves_db)
        result = await collector.collect_daily()
        assert result["period_type"] == "daily"
        assert result["total_episodes"] == 0
        assert result["growth_score"] >= 0

    @pytest.mark.asyncio
    async def test_collect_daily_idempotent(self, curves_db: Database) -> None:
        collector = SnapshotCollector(curves_db)
        r1 = await collector.collect_daily("2026-06-01")
        r2 = await collector.collect_daily("2026-06-01")
        assert r1["id"] == r2["id"]

    @pytest.mark.asyncio
    async def test_list_snapshots(self, curves_db: Database) -> None:
        collector = SnapshotCollector(curves_db)
        await collector.collect_daily("2026-06-01")
        await collector.collect_daily("2026-06-02")
        snapshots = await collector.list_snapshots("daily")
        assert len(snapshots) == 2

    @pytest.mark.asyncio
    async def test_collect_with_episodes(self, curves_db: Database) -> None:
        from ulid import ULID

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        await curves_db.execute(
            """INSERT INTO episode
               (id, goal, outcome, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (str(ULID()), "test task", "SUCCESS", now, now),
        )
        await curves_db.commit()

        collector = SnapshotCollector(curves_db)
        result = await collector.collect_daily(today)
        assert result["total_episodes"] == 1
        assert result["success"] == 1
        assert result["success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_growth_score_range(self, curves_db: Database) -> None:
        collector = SnapshotCollector(curves_db)
        result = await collector.collect_daily()
        assert 0 <= result["growth_score"] <= 100


class TestImprovementDigest:
    @pytest.mark.asyncio
    async def test_empty_digest(self, curves_db: Database) -> None:
        d = ImprovementDigest(curves_db)
        result = await d.weekly_digest()
        assert "No data" in result

    @pytest.mark.asyncio
    async def test_digest_with_data(self, curves_db: Database) -> None:
        collector = SnapshotCollector(curves_db)
        for i in range(3):
            await collector.collect_daily(f"2026-06-{i+1:02d}")

        d = ImprovementDigest(curves_db)
        result = await d.weekly_digest()
        assert "Weekly" in result
        assert "Success" in result

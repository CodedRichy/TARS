from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from tars.agent.context_compiler import ContextCompiler
from tars.agent.loop import AgentLoop
from tars.agent.permissions import PermissionManager
from tars.core.db import Database
from tars.gateway.action_ledger import ActionLedger
from tars.genome.lesson_server import LessonServer
from tars.genome.models import HeuristicStatus, Outcome
from tars.genome.store import GenomeStore
from tars.router.model_router import ModelRouter
from tars.tools.base import Tool


@dataclass
class EvalTask:
    goal: str
    domain: str = ""
    tags: list[str] = field(default_factory=list)
    expected_outcome: str = "SUCCESS"


@dataclass
class EvalResult:
    task: EvalTask
    with_lessons: Outcome | None = None
    without_lessons: Outcome | None = None

    @property
    def lesson_helped(self) -> bool | None:
        if self.with_lessons is None or self.without_lessons is None:
            return None
        if self.with_lessons == Outcome.SUCCESS and self.without_lessons != Outcome.SUCCESS:
            return True
        if self.with_lessons != Outcome.SUCCESS and self.without_lessons == Outcome.SUCCESS:
            return False
        return None


@dataclass
class EvalSummary:
    total: int = 0
    with_lessons_success: int = 0
    without_lessons_success: int = 0
    results: list[EvalResult] = field(default_factory=list)

    @property
    def lift(self) -> float:
        if self.total == 0:
            return 0.0
        with_rate = self.with_lessons_success / self.total
        without_rate = self.without_lessons_success / self.total
        return with_rate - without_rate

    @property
    def lift_pct(self) -> float:
        if self.without_lessons_success == 0:
            return float("inf") if self.with_lessons_success > 0 else 0.0
        return (self.lift / (self.without_lessons_success / self.total)) * 100

    @property
    def p_value(self) -> float:
        n_plus = sum(
            1
            for r in self.results
            if r.with_lessons == Outcome.SUCCESS and r.without_lessons != Outcome.SUCCESS
        )
        n_minus = sum(
            1
            for r in self.results
            if r.with_lessons != Outcome.SUCCESS and r.without_lessons == Outcome.SUCCESS
        )
        n = n_plus + n_minus
        if n == 0:
            return 1.0
        chi2 = ((abs(n_plus - n_minus) - 1) ** 2) / n if n > 0 else 0
        if chi2 > 10.83:
            return 0.001
        if chi2 > 6.63:
            return 0.01
        if chi2 > 3.84:
            return 0.05
        return 0.1 if chi2 > 2.71 else 1.0

    def render_text(self) -> str:
        lines = [
            "## TARS A/B Eval Results",
            f"Total tasks: {self.total}",
            f"With lessons:    {self.with_lessons_success}/{self.total} success",
            f"Without lessons: {self.without_lessons_success}/{self.total} success",
            f"Lift: {self.lift:.1%} ({self.lift_pct:+.1f}%)",
            f"p-value: {self.p_value}",
        ]
        sig = "significant" if self.p_value <= 0.05 else "not significant"
        lines.append(f"Result: {sig}")
        return "\n".join(lines)


def load_suite(path: Path) -> list[EvalTask]:
    data = json.loads(path.read_text())
    tasks = []
    for item in data:
        tasks.append(
            EvalTask(
                goal=item["goal"],
                domain=item.get("domain", ""),
                tags=item.get("tags", []),
                expected_outcome=item.get("expected_outcome", "SUCCESS"),
            )
        )
    return tasks


class EvalHarness:
    def __init__(
        self,
        router: ModelRouter,
        db: Database,
        tools: dict[str, Tool],
    ) -> None:
        self.router = router
        self.db = db
        self.tools = tools

    async def run_suite(self, tasks: list[EvalTask]) -> EvalSummary:
        summary = EvalSummary(total=len(tasks))

        for task in tasks:
            result = EvalResult(task=task)

            result.with_lessons = await self._run_task(task, use_lessons=True)
            if result.with_lessons == Outcome.SUCCESS:
                summary.with_lessons_success += 1

            result.without_lessons = await self._run_task(task, use_lessons=False)
            if result.without_lessons == Outcome.SUCCESS:
                summary.without_lessons_success += 1

            summary.results.append(result)

        return summary

    async def _run_task(self, task: EvalTask, use_lessons: bool) -> Outcome:
        store = GenomeStore(self.db)
        perms = PermissionManager(self.db)
        ledger = ActionLedger(self.db)
        lesson_server = LessonServer(store)
        compiler = ContextCompiler(lesson_server)

        if not use_lessons:
            originals = await store.list_heuristics(status=HeuristicStatus.ACTIVE)
            for h in originals:
                await store.update_heuristic_status(h.id, HeuristicStatus.DEPRECATED)

        agent = AgentLoop(
            router=self.router,
            permissions=perms,
            ledger=ledger,
            genome_store=store,
            context_compiler=compiler,
            tools=self.tools,
        )

        for tool_name in self.tools:
            await perms.grant(f"tool.{tool_name}")

        try:
            loop_result = await agent.run(
                goal=task.goal,
                domain=task.domain,
                tags=task.tags,
            )
            return loop_result.outcome
        except Exception:
            return Outcome.FAILURE
        finally:
            if not use_lessons:
                for h in originals:
                    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

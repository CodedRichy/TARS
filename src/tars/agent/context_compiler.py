from __future__ import annotations

from dataclasses import dataclass, field

from tars.genome.lesson_server import LessonServer, ScoredHeuristic, TaskContext
from tars.genome.models import FailureModel


@dataclass
class CompiledContext:
    goal: str
    task_state: str = ""
    lessons: list[ScoredHeuristic] = field(default_factory=list)
    failure_warnings: list[FailureModel] = field(default_factory=list)
    working_data: str = ""
    tools_available: list[str] = field(default_factory=list)
    permissions_summary: str = ""

    def render(self) -> str:
        parts = [f"## Goal\n{self.goal}"]

        if self.task_state:
            parts.append(f"\n## Current State\n{self.task_state}")

        if self.lessons:
            lesson_lines = []
            for sl in self.lessons:
                h = sl.heuristic
                lesson_lines.append(
                    f"- [{h.confidence:.0%}] {h.statement} (scope: {h.scope.summary})"
                )
            parts.append("\n## Lessons\n" + "\n".join(lesson_lines))

        if self.failure_warnings:
            warn_lines = []
            for fm in self.failure_warnings:
                warn_lines.append(f"- ⚠ {fm.signature}: {fm.root_cause}")
            parts.append("\n## Failure Warnings\n" + "\n".join(warn_lines))

        if self.tools_available:
            parts.append("\n## Available Tools\n" + ", ".join(self.tools_available))

        if self.permissions_summary:
            parts.append(f"\n## Permissions\n{self.permissions_summary}")

        if self.working_data:
            parts.append(f"\n## Working Data\n{self.working_data}")

        return "\n".join(parts)


class ContextCompiler:
    def __init__(self, lesson_server: LessonServer) -> None:
        self.lesson_server = lesson_server

    async def compile(
        self,
        goal: str,
        domain: str = "",
        tools: list[str] | None = None,
        tags: list[str] | None = None,
        task_state: str = "",
        working_data: str = "",
        permissions_summary: str = "",
        top_k: int = 5,
    ) -> CompiledContext:
        ctx = TaskContext(
            goal=goal,
            domain=domain,
            tools=tools or [],
            tags=tags or [],
        )

        lessons = await self.lesson_server.serve(ctx, top_k=top_k)
        failure_warnings = await self.lesson_server.check_failure_models(ctx)

        return CompiledContext(
            goal=goal,
            task_state=task_state,
            lessons=lessons,
            failure_warnings=failure_warnings,
            working_data=working_data,
            tools_available=tools or [],
            permissions_summary=permissions_summary,
        )

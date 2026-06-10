from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ulid import ULID

from tars.agent.context_compiler import ContextCompiler
from tars.agent.permissions import PermissionDeniedError, PermissionManager
from tars.agent.planner import Plan, Planner, PlanStep
from tars.core.events import Event, EventBus, EventType
from tars.gateway.action_ledger import ActionLedger
from tars.genome.models import CostBreakdown, Episode, Outcome
from tars.genome.store import GenomeStore
from tars.router.model_router import ModelRouter
from tars.tools.base import Tool, ToolResult


class StepStatus(enum.StrEnum):
    PENDING = "pending"
    PERMISSION_DENIED = "permission_denied"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    step: PlanStep
    status: StepStatus
    tool_result: ToolResult | None = None
    error: str = ""


@dataclass
class LoopResult:
    goal: str
    plan: Plan
    step_results: list[StepResult] = field(default_factory=list)
    outcome: Outcome = Outcome.SUCCESS
    episode_id: str | None = None
    total_cost_inr: float = 0.0

    @property
    def succeeded(self) -> bool:
        return self.outcome == Outcome.SUCCESS

    @property
    def summary(self) -> str:
        ok = sum(1 for r in self.step_results if r.status == StepStatus.SUCCESS)
        total = len(self.step_results)
        return f"{self.outcome.value}: {ok}/{total} steps completed (₹{self.total_cost_inr:.4f})"


class AgentLoop:
    def __init__(
        self,
        router: ModelRouter,
        permissions: PermissionManager,
        ledger: ActionLedger,
        genome_store: GenomeStore,
        context_compiler: ContextCompiler,
        tools: dict[str, Tool],
        event_bus: EventBus | None = None,
    ) -> None:
        self.router = router
        self.permissions = permissions
        self.ledger = ledger
        self.genome_store = genome_store
        self.context_compiler = context_compiler
        self.tools = tools
        self.event_bus = event_bus
        self.planner = Planner(router)

    def _emit(self, event_type: EventType, session_id: str, **data: object) -> None:
        if self.event_bus is not None:
            self.event_bus.emit_nowait(
                Event(type=event_type, data=data, session_id=session_id)
            )

    async def run(
        self,
        goal: str,
        session_id: str | None = None,
        domain: str = "",
        tags: list[str] | None = None,
    ) -> LoopResult:
        session_id = session_id or str(ULID())
        tool_names = list(self.tools.keys())

        compiled = await self.context_compiler.compile(
            goal=goal,
            domain=domain,
            tools=tool_names,
            tags=tags,
        )

        plan = await self.planner.create_plan(
            goal=goal,
            context=compiled.render(),
            available_tools=tool_names,
        )

        result = LoopResult(goal=goal, plan=plan)
        started_at = datetime.now(UTC)

        self._emit(
            EventType.TASK_STARTED,
            session_id,
            goal=goal,
            step_count=plan.step_count,
            reasoning=plan.reasoning,
        )

        for step in plan.steps:
            self._emit(
                EventType.STEP_STARTED,
                session_id,
                step_index=step.index,
                tool=step.tool,
                description=step.description,
            )

            step_result = await self._execute_step(step, session_id)
            result.step_results.append(step_result)

            self._emit(
                EventType.STEP_COMPLETED,
                session_id,
                step_index=step.index,
                tool=step.tool,
                status=step_result.status.value,
                output=(step_result.tool_result.output[:500] if step_result.tool_result else ""),
                error=step_result.error,
            )

            if step_result.status == StepStatus.PERMISSION_DENIED:
                result.outcome = Outcome.ABORTED
                break
            if step_result.status == StepStatus.FAILED:
                result.outcome = Outcome.PARTIAL
                break

        completed_at = datetime.now(UTC)

        if all(r.status == StepStatus.SUCCESS for r in result.step_results):
            result.outcome = Outcome.SUCCESS
        elif any(r.status == StepStatus.SUCCESS for r in result.step_results):
            result.outcome = Outcome.PARTIAL

        episode = Episode(
            id="",
            goal=goal,
            context_features={"domain": domain, "tags": tags or []},
            action_trace=[
                {
                    "step": r.step.index,
                    "tool": r.step.tool,
                    "status": r.status.value,
                    "output": (r.tool_result.output[:200] if r.tool_result else ""),
                }
                for r in result.step_results
            ],
            outcome=result.outcome,
            cost_breakdown=CostBreakdown(total_inr=result.total_cost_inr),
            lessons_applied=[sl.heuristic.id for sl in compiled.lessons],
            started_at=started_at,
            completed_at=completed_at,
        )
        result.episode_id = await self.genome_store.insert_episode(episode)

        event_type = (
            EventType.TASK_COMPLETED
            if result.outcome == Outcome.SUCCESS
            else EventType.TASK_FAILED
        )
        self._emit(
            event_type,
            session_id,
            goal=goal,
            outcome=result.outcome.value,
            summary=result.summary,
            episode_id=result.episode_id,
            cost_inr=result.total_cost_inr,
        )

        return result

    async def _execute_step(self, step: PlanStep, session_id: str) -> StepResult:
        tool = self.tools.get(step.tool)
        if not tool:
            return StepResult(
                step=step,
                status=StepStatus.FAILED,
                error=f"Unknown tool: {step.tool}",
            )

        if step.requires_permission:
            self._emit(
                EventType.PERMISSION_REQUESTED,
                session_id,
                capability=step.requires_permission,
                step_index=step.index,
                tool=step.tool,
                description=step.description,
            )
            try:
                await self.permissions.require(step.requires_permission)
            except PermissionDeniedError as e:
                self._emit(
                    EventType.PERMISSION_DENIED,
                    session_id,
                    capability=step.requires_permission,
                    reason=str(e),
                )
                await self.ledger.append(
                    session_id=session_id,
                    tool=step.tool,
                    action=step.description,
                    plan_step=str(step.index),
                    result=f"DENIED: {e}",
                )
                return StepResult(
                    step=step,
                    status=StepStatus.PERMISSION_DENIED,
                    error=str(e),
                )
            self._emit(
                EventType.PERMISSION_GRANTED,
                session_id,
                capability=step.requires_permission,
            )

        validation_err = tool.validate_params(step.tool_args)
        if validation_err:
            return StepResult(step=step, status=StepStatus.FAILED, error=validation_err)

        tool_result = await tool.execute(**step.tool_args)

        await self.ledger.append(
            session_id=session_id,
            tool=step.tool,
            action=step.description,
            plan_step=str(step.index),
            result="OK" if tool_result.success else tool_result.error,
        )

        return StepResult(
            step=step,
            status=(StepStatus.SUCCESS if tool_result.success else StepStatus.FAILED),
            tool_result=tool_result,
        )

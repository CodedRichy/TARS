from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tars.agent.context_compiler import ContextCompiler
from tars.agent.loop import AgentLoop, StepStatus
from tars.agent.permissions import PermissionManager
from tars.agent.planner import Plan, PlanStep
from tars.core.db import Database
from tars.gateway.action_ledger import ActionLedger
from tars.genome.lesson_server import LessonServer
from tars.genome.models import Outcome
from tars.genome.store import GenomeStore
from tars.router.model_router import ModelRouter
from tars.tools.filesystem import ReadFileTool, WriteFileTool
from tars.tools.shell import ShellTool

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def loop_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def agent_loop(loop_db: Database) -> AgentLoop:
    store = GenomeStore(loop_db)
    perms = PermissionManager(loop_db)
    ledger = ActionLedger(loop_db)
    lesson_server = LessonServer(store)
    compiler = ContextCompiler(lesson_server)

    tools = {
        "shell": ShellTool(),
        "read_file": ReadFileTool(),
        "write_file": WriteFileTool(),
    }

    mock_router = AsyncMock(spec=ModelRouter)
    return AgentLoop(
        router=mock_router,
        permissions=perms,
        ledger=ledger,
        genome_store=store,
        context_compiler=compiler,
        tools=tools,
    )


def _mock_plan(goal: str, steps: list[PlanStep]) -> Plan:
    return Plan(goal=goal, steps=steps, reasoning="test plan")


@pytest.mark.asyncio
async def test_step_denied_without_permission(
    agent_loop: AgentLoop,
) -> None:
    plan = _mock_plan(
        "list files",
        [
            PlanStep(
                index=1,
                description="list /tmp",
                tool="shell",
                tool_args={"command": "echo test"},
                requires_permission="tool.shell",
            )
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("list files", session_id="test-sess")

    assert result.outcome == Outcome.ABORTED
    assert result.step_results[0].status == StepStatus.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_step_succeeds_with_permission(
    agent_loop: AgentLoop,
) -> None:
    await agent_loop.permissions.grant("tool.shell")

    plan = _mock_plan(
        "echo test",
        [
            PlanStep(
                index=1,
                description="echo hello",
                tool="shell",
                tool_args={"command": "echo hello"},
                requires_permission="tool.shell",
            )
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("echo test", session_id="test-sess")

    assert result.outcome == Outcome.SUCCESS
    assert result.step_results[0].status == StepStatus.SUCCESS
    assert "hello" in result.step_results[0].tool_result.output


@pytest.mark.asyncio
async def test_unknown_tool_fails(agent_loop: AgentLoop) -> None:
    plan = _mock_plan(
        "test",
        [PlanStep(index=1, description="nope", tool="nonexistent", tool_args={})],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("test", session_id="test-sess")

    assert result.step_results[0].status == StepStatus.FAILED
    assert "Unknown tool" in result.step_results[0].error


@pytest.mark.asyncio
async def test_episode_recorded(agent_loop: AgentLoop) -> None:
    await agent_loop.permissions.grant("tool.shell")

    plan = _mock_plan(
        "record test",
        [
            PlanStep(
                index=1,
                description="echo hi",
                tool="shell",
                tool_args={"command": "echo hi"},
                requires_permission="tool.shell",
            )
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("record test", session_id="test-sess")

    assert result.episode_id is not None
    ep = await agent_loop.genome_store.get_episode(result.episode_id)
    assert ep is not None
    assert ep.goal == "record test"
    assert ep.outcome == Outcome.SUCCESS


@pytest.mark.asyncio
async def test_action_ledger_populated(agent_loop: AgentLoop) -> None:
    await agent_loop.permissions.grant("tool.shell")

    plan = _mock_plan(
        "ledger test",
        [
            PlanStep(
                index=1,
                description="echo x",
                tool="shell",
                tool_args={"command": "echo x"},
                requires_permission="tool.shell",
            )
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        await agent_loop.run("ledger test", session_id="ledger-sess")

    actions = await agent_loop.ledger.get_session_actions("ledger-sess")
    assert len(actions) == 1
    assert actions[0]["tool"] == "shell"


@pytest.mark.asyncio
async def test_multi_step_partial_failure(agent_loop: AgentLoop) -> None:
    await agent_loop.permissions.grant("tool.shell")

    plan = _mock_plan(
        "multi step",
        [
            PlanStep(
                index=1,
                description="echo ok",
                tool="shell",
                tool_args={"command": "echo ok"},
                requires_permission="tool.shell",
            ),
            PlanStep(
                index=2,
                description="fail step",
                tool="shell",
                tool_args={"command": "exit 1"},
                requires_permission="tool.shell",
            ),
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("multi step", session_id="multi-sess")

    assert result.outcome == Outcome.PARTIAL
    assert result.step_results[0].status == StepStatus.SUCCESS
    assert result.step_results[1].status == StepStatus.FAILED


@pytest.mark.asyncio
async def test_no_permission_required_step(agent_loop: AgentLoop) -> None:
    plan = _mock_plan(
        "no perm",
        [
            PlanStep(
                index=1,
                description="echo hello",
                tool="shell",
                tool_args={"command": "echo hello"},
                requires_permission="",
            )
        ],
    )

    with patch.object(agent_loop.planner, "create_plan", return_value=plan):
        result = await agent_loop.run("no perm", session_id="no-perm-sess")

    assert result.outcome == Outcome.SUCCESS

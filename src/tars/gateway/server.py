from __future__ import annotations

from typing import Any

from tars.agent.context_compiler import ContextCompiler
from tars.agent.loop import AgentLoop, LoopResult
from tars.agent.permissions import PermissionManager
from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.core.events import EventBus
from tars.gateway.action_ledger import ActionLedger
from tars.gateway.kill_switch import KillSwitch
from tars.gateway.session import Session, SessionManager
from tars.genome.lesson_server import LessonServer
from tars.genome.store import GenomeStore
from tars.mcp.manager import MCPManager
from tars.router.model_router import ModelRouter
from tars.tools.base import Tool
from tars.tools.registry import create_default_registry


class GatewayServer:
    def __init__(self, config: TarsConfig, db: Database) -> None:
        self.config = config
        self.db = db
        self.event_bus = EventBus()
        self.session_manager = SessionManager()

        self.genome_store = GenomeStore(db)
        self.permissions = PermissionManager(db)
        self.ledger = ActionLedger(db)
        self.router = ModelRouter(config, db)
        self.lesson_server = LessonServer(self.genome_store)
        self.context_compiler = ContextCompiler(self.lesson_server)

        self.kill_switch = KillSwitch(self.session_manager, self.permissions, self.event_bus)

        self.tool_registry = create_default_registry()
        self._register_extended_tools()
        self.mcp_manager = MCPManager(self.tool_registry)
        self.tools: dict[str, Tool] = self.tool_registry.to_dict()

    def _register_extended_tools(self) -> None:
        from tars.tools.calendar import CalendarTool
        from tars.tools.code_analysis import CodeAnalysisTool
        from tars.tools.database import DatabaseTool
        from tars.tools.docker import DockerTool
        from tars.tools.git import GitTool
        from tars.tools.web_search import WebSearchTool

        self.tool_registry.register(GitTool())
        self.tool_registry.register(CodeAnalysisTool())
        self.tool_registry.register(DockerTool())
        self.tool_registry.register(DatabaseTool())
        self.tool_registry.register(WebSearchTool())
        self.tool_registry.register(CalendarTool())

    async def start_mcp_servers(self) -> dict[str, int | str]:
        from tars.mcp.types import MCPServerConfig, TransportType

        configs: list[MCPServerConfig] = []
        for name, entry in self.config.mcp.servers.items():
            configs.append(
                MCPServerConfig(
                    name=name,
                    transport=TransportType(entry.transport),
                    command=entry.command,
                    args=entry.args,
                    env=entry.env,
                    url=entry.url,
                    headers=entry.headers,
                )
            )

        if not configs:
            return {}

        results = await self.mcp_manager.connect_all(configs)
        self.tools = self.tool_registry.to_dict()
        return results

    async def stop_mcp_servers(self) -> None:
        await self.mcp_manager.disconnect_all()

    def create_agent_loop(self) -> AgentLoop:
        return AgentLoop(
            router=self.router,
            permissions=self.permissions,
            ledger=self.ledger,
            genome_store=self.genome_store,
            context_compiler=self.context_compiler,
            tools=self.tools,
            event_bus=self.event_bus,
        )

    async def submit_task(
        self, session: Session, goal: str, domain: str = "", tags: list[str] | None = None
    ) -> LoopResult:
        if self.kill_switch.is_triggered:
            from tars.agent.loop import LoopResult
            from tars.agent.planner import Plan
            from tars.genome.models import Outcome

            return LoopResult(
                goal=goal,
                plan=Plan(goal=goal, reasoning="Kill switch active"),
                outcome=Outcome.ABORTED,
            )

        session.start_task(goal)
        agent = self.create_agent_loop()

        try:
            result = await agent.run(
                goal=goal,
                session_id=session.id,
                domain=domain,
                tags=tags,
            )
            session.complete_task(result.total_cost_inr)
            return result
        except Exception:
            session.complete_task()
            raise

    async def handle_rpc(self, request: dict) -> dict[str, Any]:
        method = request.get("method", "")
        params = request.get("params", {})

        if method == "submit_task":
            session_id = params.get("session_id")
            session = (
                self.session_manager.get(session_id)
                if session_id
                else self.session_manager.create()
            )
            if not session:
                return {"error": "Invalid session"}

            result = await self.submit_task(
                session,
                goal=params.get("goal", ""),
                domain=params.get("domain", ""),
                tags=params.get("tags"),
            )
            return {
                "result": {
                    "outcome": result.outcome.value,
                    "summary": result.summary,
                    "episode_id": result.episode_id,
                }
            }

        if method == "get_status":
            sessions = self.session_manager.get_active()
            budget = await self.router.get_budget_status()
            return {
                "result": {
                    "active_sessions": len(sessions),
                    "budget": budget,
                    "kill_switch": self.kill_switch.is_triggered,
                }
            }

        if method == "kill":
            reason = params.get("reason", "RPC kill")
            info = await self.kill_switch.trigger(reason)
            return {"result": info}

        if method == "grant_permission":
            perm = await self.permissions.grant(
                capability=params.get("capability", ""),
                scope=params.get("scope", "*"),
            )
            return {
                "result": {
                    "id": perm.id,
                    "capability": perm.capability,
                    "scope": perm.scope,
                }
            }

        return {"error": f"Unknown method: {method}"}

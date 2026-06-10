from __future__ import annotations

import asyncio
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_OUTPUT = 50_000
TIMEOUT_S = 120

ALLOWED_SUBCOMMANDS = frozenset({
    "ps", "images", "build", "run", "stop", "rm", "logs",
    "exec", "inspect", "pull", "push", "tag", "network",
    "volume", "compose", "stats", "top", "port", "version",
})

BLOCKED_FLAGS = frozenset({"--privileged", "--cap-add=ALL"})


class DockerTool(Tool):
    @property
    def name(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return "Manage Docker containers: ps, build, run, stop, logs, exec, compose, etc."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "description": "Docker subcommand (ps, build, run, stop, logs, etc.)",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments for the subcommand",
                    "default": [],
                },
            },
            "required": ["subcommand"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        subcommand = kwargs.get("subcommand", "")
        args: list[str] = kwargs.get("args", [])

        if subcommand not in ALLOWED_SUBCOMMANDS:
            return ToolResult(
                success=False,
                error=f"Subcommand not allowed: {subcommand}",
            )

        for arg in args:
            if arg in BLOCKED_FLAGS:
                return ToolResult(success=False, error=f"Blocked flag: {arg}")

        cmd = ["docker", subcommand, *args]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_S)

            out = stdout.decode(errors="replace")[:MAX_OUTPUT]
            err = stderr.decode(errors="replace")[:MAX_OUTPUT]

            return ToolResult(
                success=proc.returncode == 0,
                output=out,
                error=err if proc.returncode != 0 else "",
                data={"return_code": proc.returncode},
            )
        except TimeoutError:
            return ToolResult(success=False, error=f"Docker command timed out after {TIMEOUT_S}s")
        except FileNotFoundError:
            return ToolResult(success=False, error="docker not found in PATH")
        except OSError as e:
            return ToolResult(success=False, error=str(e))

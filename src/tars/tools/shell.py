from __future__ import annotations

import asyncio
from typing import Any

from tars.tools.base import Tool, ToolResult

BLOCKED_COMMANDS = frozenset(
    {
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero",
        ":(){ :|:& };:",
        "> /dev/sda",
    }
)

MAX_OUTPUT_CHARS = 50_000
DEFAULT_TIMEOUT_S = 30


class ShellTool(Tool):
    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": DEFAULT_TIMEOUT_S,
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the command",
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT_S)
        working_dir = kwargs.get("working_dir")

        if not command.strip():
            return ToolResult(success=False, error="Empty command")

        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult(success=False, error="Blocked: dangerous command pattern")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            out = stdout.decode(errors="replace")[:MAX_OUTPUT_CHARS]
            err = stderr.decode(errors="replace")[:MAX_OUTPUT_CHARS]

            return ToolResult(
                success=proc.returncode == 0,
                output=out,
                error=err,
                data={"return_code": proc.returncode},
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                error=f"Command timed out after {timeout}s",
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e))

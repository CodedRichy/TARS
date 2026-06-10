from __future__ import annotations

import asyncio
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_OUTPUT = 50_000
TIMEOUT_S = 60

ALLOWED_SUBCOMMANDS = frozenset({
    "status", "log", "diff", "show", "branch", "checkout",
    "add", "commit", "push", "pull", "fetch", "clone",
    "stash", "tag", "remote", "rev-parse", "blame",
    "merge", "rebase", "cherry-pick", "reset",
})


class GitTool(Tool):
    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return "Execute git commands: status, log, diff, commit, push, pull, clone, branch, etc."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "subcommand": {
                    "type": "string",
                    "description": "Git subcommand (status, log, diff, commit, etc.)",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Arguments to pass to the git subcommand",
                    "default": [],
                },
                "working_dir": {
                    "type": "string",
                    "description": "Repository directory",
                },
            },
            "required": ["subcommand"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        subcommand = kwargs.get("subcommand", "")
        args: list[str] = kwargs.get("args", [])
        working_dir = kwargs.get("working_dir")

        if subcommand not in ALLOWED_SUBCOMMANDS:
            return ToolResult(
                success=False,
                error=(
                    f"Subcommand not allowed: {subcommand}. "
                    f"Allowed: {sorted(ALLOWED_SUBCOMMANDS)}"
                ),
            )

        cmd = ["git", subcommand, *args]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
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
            return ToolResult(success=False, error=f"Git command timed out after {TIMEOUT_S}s")
        except FileNotFoundError:
            return ToolResult(success=False, error="git not found in PATH")
        except OSError as e:
            return ToolResult(success=False, error=str(e))

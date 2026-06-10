from __future__ import annotations

import asyncio
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_OUTPUT = 50_000
TIMEOUT_S = 60


class SSHTool(Tool):
    @property
    def name(self) -> str:
        return "ssh"

    @property
    def description(self) -> str:
        return "Execute commands on remote hosts via SSH."

    @property
    def required_capability(self) -> str:
        return "tool.ssh"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Remote hostname or IP"},
                "command": {"type": "string", "description": "Command to execute remotely"},
                "user": {"type": "string", "description": "SSH username", "default": ""},
                "port": {"type": "integer", "description": "SSH port", "default": 22},
                "identity_file": {
                    "type": "string",
                    "description": "Path to SSH private key",
                },
            },
            "required": ["host", "command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        host = kwargs.get("host", "")
        command = kwargs.get("command", "")
        user = kwargs.get("user", "")
        port = kwargs.get("port", 22)
        identity_file = kwargs.get("identity_file")

        if not host or not command:
            return ToolResult(success=False, error="host and command are required")

        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]

        if identity_file:
            ssh_cmd.extend(["-i", identity_file])
        if port != 22:
            ssh_cmd.extend(["-p", str(port)])

        target = f"{user}@{host}" if user else host
        ssh_cmd.extend([target, command])

        try:
            proc = await asyncio.create_subprocess_exec(
                *ssh_cmd,
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
                data={"return_code": proc.returncode, "host": host},
            )
        except TimeoutError:
            return ToolResult(success=False, error=f"SSH command timed out after {TIMEOUT_S}s")
        except FileNotFoundError:
            return ToolResult(success=False, error="ssh not found in PATH")
        except OSError as e:
            return ToolResult(success=False, error=str(e))

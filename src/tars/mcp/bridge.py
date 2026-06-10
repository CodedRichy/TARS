from __future__ import annotations

import json
from typing import Any

from tars.mcp.client import MCPClient
from tars.mcp.types import MCPToolDefinition
from tars.tools.base import Tool, ToolResult


class MCPToolBridge(Tool):
    """Wraps an MCP tool as a TARS Tool so it can be registered in ToolRegistry."""

    def __init__(self, definition: MCPToolDefinition, client: MCPClient) -> None:
        self._definition = definition
        self._client = client
        self._tool_name = f"mcp.{definition.server_name}.{definition.name}"

    @property
    def name(self) -> str:
        return self._tool_name

    @property
    def description(self) -> str:
        return self._definition.description or f"MCP tool: {self._definition.name}"

    @property
    def parameters_schema(self) -> dict:
        schema = self._definition.input_schema
        if not schema:
            return {"type": "object", "properties": {}}
        return schema

    @property
    def required_capability(self) -> str:
        return f"tool.mcp.{self._definition.server_name}"

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not self._client.is_initialized:
            return ToolResult(
                success=False,
                error=f"MCP server '{self._definition.server_name}' not connected",
            )

        try:
            result = await self._client.call_tool(
                self._definition.name, arguments=kwargs
            )
        except (RuntimeError, TimeoutError, ConnectionError) as exc:
            return ToolResult(success=False, error=str(exc))

        content_parts = result.get("content", [])
        is_error = result.get("isError", False)

        text_parts: list[str] = []
        data: dict[str, Any] = {}
        for part in content_parts:
            part_type = part.get("type", "text")
            if part_type == "text":
                text_parts.append(part.get("text", ""))
            elif part_type == "image":
                data["image"] = part.get("data", "")
                data["mime_type"] = part.get("mimeType", "")
                text_parts.append("[image data]")
            elif part_type == "resource":
                resource = part.get("resource", {})
                text_parts.append(resource.get("text", ""))
                data["resource_uri"] = resource.get("uri", "")

        output = "\n".join(text_parts)

        if is_error:
            return ToolResult(success=False, error=output, data=data)

        return ToolResult(success=True, output=output, data=data)

    def __repr__(self) -> str:
        return (
            f"MCPToolBridge(name={self._tool_name!r}, "
            f"server={self._definition.server_name!r})"
        )


def _format_content(content: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in content:
        if item.get("type") == "text":
            parts.append(item.get("text", ""))
        elif item.get("type") == "image":
            parts.append("[image]")
        else:
            parts.append(json.dumps(item))
    return "\n".join(parts)

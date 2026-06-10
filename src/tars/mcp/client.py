from __future__ import annotations

from typing import Any

from tars.core.log import get_logger
from tars.mcp.transport import MCPTransport
from tars.mcp.types import (
    MCP_PROTOCOL_VERSION,
    JSONRPCRequest,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
)

logger = get_logger("mcp.client")


class MCPClient:
    def __init__(self, server_config: MCPServerConfig, transport: MCPTransport) -> None:
        self._config = server_config
        self._transport = transport
        self._server_name = server_config.name
        self._server_info: dict[str, Any] = {}
        self._capabilities: dict[str, Any] = {}
        self._initialized = False

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def capabilities(self) -> dict[str, Any]:
        return self._capabilities

    async def connect(self) -> None:
        await self._transport.start()
        await self._initialize()

    async def _initialize(self) -> None:
        resp = await self._transport.send(
            JSONRPCRequest(
                method="initialize",
                params={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "tars",
                        "version": "0.2.0",
                    },
                },
            )
        )

        if resp.is_error:
            raise ConnectionError(
                f"MCP initialize failed for {self._server_name}: {resp.error}"
            )

        result = resp.result or {}
        self._server_info = result.get("serverInfo", {})
        self._capabilities = result.get("capabilities", {})

        await self._transport.send(
            JSONRPCRequest(method="notifications/initialized", params={})
        )

        self._initialized = True
        logger.info(
            "MCP server '%s' initialized (version: %s)",
            self._server_name,
            self._server_info.get("version", "unknown"),
        )

    async def list_tools(self) -> list[MCPToolDefinition]:
        resp = await self._transport.send(
            JSONRPCRequest(method="tools/list", params={})
        )

        if resp.is_error:
            logger.warning("tools/list failed for %s: %s", self._server_name, resp.error)
            return []

        result = resp.result or {}
        tools_raw = result.get("tools", [])
        tools: list[MCPToolDefinition] = []
        for t in tools_raw:
            tools.append(
                MCPToolDefinition(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=self._server_name,
                )
            )

        logger.info(
            "discovered %d tools from '%s': %s",
            len(tools),
            self._server_name,
            [t.name for t in tools],
        )
        return tools

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resp = await self._transport.send(
            JSONRPCRequest(
                method="tools/call",
                params={
                    "name": tool_name,
                    "arguments": arguments or {},
                },
            )
        )

        if resp.is_error:
            error = resp.error or {}
            raise RuntimeError(
                f"MCP tool call failed ({self._server_name}/{tool_name}): "
                f"{error.get('message', 'unknown error')}"
            )

        return resp.result or {}

    async def list_resources(self) -> list[MCPResourceDefinition]:
        if "resources" not in self._capabilities:
            return []

        resp = await self._transport.send(
            JSONRPCRequest(method="resources/list", params={})
        )

        if resp.is_error:
            logger.warning(
                "resources/list failed for %s: %s", self._server_name, resp.error
            )
            return []

        result = resp.result or {}
        return [
            MCPResourceDefinition(
                uri=r.get("uri", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                mime_type=r.get("mimeType", "text/plain"),
                server_name=self._server_name,
            )
            for r in result.get("resources", [])
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        resp = await self._transport.send(
            JSONRPCRequest(
                method="resources/read",
                params={"uri": uri},
            )
        )

        if resp.is_error:
            raise RuntimeError(
                f"MCP resource read failed ({self._server_name}, {uri}): "
                f"{(resp.error or {}).get('message', 'unknown')}"
            )

        return resp.result or {}

    async def list_prompts(self) -> list[MCPPromptDefinition]:
        if "prompts" not in self._capabilities:
            return []

        resp = await self._transport.send(
            JSONRPCRequest(method="prompts/list", params={})
        )

        if resp.is_error:
            return []

        result = resp.result or {}
        return [
            MCPPromptDefinition(
                name=p.get("name", ""),
                description=p.get("description", ""),
                arguments=p.get("arguments", []),
                server_name=self._server_name,
            )
            for p in result.get("prompts", [])
        ]

    async def close(self) -> None:
        self._initialized = False
        await self._transport.close()
        logger.info("MCP client '%s' closed", self._server_name)

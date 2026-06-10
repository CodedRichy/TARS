from __future__ import annotations

from typing import Any

from tars.core.log import get_logger
from tars.mcp.bridge import MCPToolBridge
from tars.mcp.client import MCPClient
from tars.mcp.transport import HttpTransport, MCPTransport, StdioTransport
from tars.mcp.types import MCPServerConfig, TransportType
from tars.tools.registry import ToolRegistry

logger = get_logger("mcp.manager")


class MCPManager:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._clients: dict[str, MCPClient] = {}
        self._bridges: dict[str, MCPToolBridge] = {}

    @property
    def connected_servers(self) -> list[str]:
        return [name for name, client in self._clients.items() if client.is_initialized]

    @property
    def tool_count(self) -> int:
        return len(self._bridges)

    def _create_transport(self, config: MCPServerConfig) -> MCPTransport:
        if config.transport == TransportType.STDIO:
            return StdioTransport(
                command=config.command,
                args=config.args,
                env=config.env,
            )
        if config.transport == TransportType.HTTP:
            return HttpTransport(
                url=config.url,
                headers=config.headers,
            )
        raise ValueError(f"unsupported transport: {config.transport}")

    async def connect_server(self, config: MCPServerConfig) -> int:
        if config.name in self._clients:
            logger.warning("server '%s' already connected, skipping", config.name)
            return 0

        transport = self._create_transport(config)
        client = MCPClient(config, transport)

        try:
            await client.connect()
        except Exception as exc:
            logger.error("failed to connect MCP server '%s': %s", config.name, exc)
            await transport.close()
            raise

        self._clients[config.name] = client

        tools = await client.list_tools()
        registered = 0
        for tool_def in tools:
            bridge = MCPToolBridge(tool_def, client)
            self._bridges[bridge.name] = bridge
            self._registry.register(bridge)
            registered += 1

        logger.info(
            "connected MCP server '%s': %d tools registered",
            config.name,
            registered,
        )
        return registered

    async def connect_all(self, configs: list[MCPServerConfig]) -> dict[str, int | str]:
        results: dict[str, int | str] = {}
        for config in configs:
            try:
                count = await self.connect_server(config)
                results[config.name] = count
            except Exception as exc:
                results[config.name] = f"error: {exc}"
                logger.error("skipping MCP server '%s': %s", config.name, exc)
        return results

    async def disconnect_server(self, name: str) -> bool:
        client = self._clients.pop(name, None)
        if not client:
            return False

        to_remove = [
            bname for bname, bridge in self._bridges.items()
            if bname.startswith(f"mcp.{name}.")
        ]
        for bname in to_remove:
            self._bridges.pop(bname, None)
            self._registry.unregister(bname)

        await client.close()
        logger.info(
            "disconnected MCP server '%s': %d tools removed", name, len(to_remove)
        )
        return True

    async def disconnect_all(self) -> None:
        names = list(self._clients.keys())
        for name in names:
            await self.disconnect_server(name)

    async def refresh_server(self, name: str) -> int:
        client = self._clients.get(name)
        if not client:
            raise ValueError(f"server '{name}' not connected")

        to_remove = [
            bname for bname in self._bridges if bname.startswith(f"mcp.{name}.")
        ]
        for bname in to_remove:
            self._bridges.pop(bname)
            self._registry.unregister(bname)

        tools = await client.list_tools()
        registered = 0
        for tool_def in tools:
            bridge = MCPToolBridge(tool_def, client)
            self._bridges[bridge.name] = bridge
            self._registry.register(bridge)
            registered += 1

        logger.info("refreshed MCP server '%s': %d tools", name, registered)
        return registered

    def get_server_info(self) -> list[dict[str, Any]]:
        info: list[dict[str, Any]] = []
        for name, client in self._clients.items():
            server_tools = [
                bname for bname in self._bridges if bname.startswith(f"mcp.{name}.")
            ]
            info.append({
                "name": name,
                "initialized": client.is_initialized,
                "capabilities": client.capabilities,
                "tools": server_tools,
            })
        return info

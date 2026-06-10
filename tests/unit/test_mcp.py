from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tars.mcp.bridge import MCPToolBridge
from tars.mcp.client import MCPClient
from tars.mcp.manager import MCPManager
from tars.mcp.transport import MCPTransport
from tars.mcp.types import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerConfig,
    MCPToolDefinition,
    TransportType,
)
from tars.tools.registry import ToolRegistry


class MockTransport(MCPTransport):
    def __init__(self) -> None:
        self._connected = False
        self._responses: list[JSONRPCResponse] = []
        self._sent: list[JSONRPCRequest] = []

    def queue_response(
        self,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self._responses.append(JSONRPCResponse(id=0, result=result, error=error))

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._connected = True

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        self._sent.append(request)
        if self._responses:
            return self._responses.pop(0)
        return JSONRPCResponse(id=request.id, result={})

    async def close(self) -> None:
        self._connected = False


def _server_config(name: str = "test-server") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        transport=TransportType.STDIO,
        command=["echo"],
    )


def _tool_def(
    name: str = "read_file", desc: str = "Read a file", server: str = "test-server"
) -> MCPToolDefinition:
    return MCPToolDefinition(
        name=name,
        description=desc,
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        server_name=server,
    )


# --- types ---


class TestTypes:
    def test_jsonrpc_request_to_dict(self) -> None:
        req = JSONRPCRequest(method="tools/list", params={"cursor": None}, id=1)
        d = req.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["method"] == "tools/list"
        assert d["id"] == 1

    def test_jsonrpc_response_from_dict(self) -> None:
        data = {"id": 1, "result": {"tools": []}}
        resp = JSONRPCResponse.from_dict(data)
        assert not resp.is_error
        assert resp.result == {"tools": []}

    def test_jsonrpc_error_response(self) -> None:
        data = {"id": 1, "error": {"code": -1, "message": "fail"}}
        resp = JSONRPCResponse.from_dict(data)
        assert resp.is_error


# --- client ---


class TestMCPClient:
    @pytest.mark.asyncio
    async def test_connect_and_initialize(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock", "version": "1.0"},
        })
        transport.queue_response(result={})  # notifications/initialized

        client = MCPClient(_server_config(), transport)
        await client.connect()

        assert client.is_initialized
        assert transport._sent[0].method == "initialize"
        assert transport._sent[1].method == "notifications/initialized"

    @pytest.mark.asyncio
    async def test_initialize_error_raises(self) -> None:
        transport = MockTransport()
        transport.queue_response(error={"code": -1, "message": "nope"})

        client = MCPClient(_server_config(), transport)
        with pytest.raises(ConnectionError, match="nope"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock", "version": "1.0"},
        })
        transport.queue_response(result={})
        transport.queue_response(result={
            "tools": [
                {"name": "read", "description": "Read file", "inputSchema": {}},
                {"name": "write", "description": "Write file", "inputSchema": {}},
            ]
        })

        client = MCPClient(_server_config(), transport)
        await client.connect()
        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0].name == "read"
        assert tools[1].name == "write"
        assert tools[0].server_name == "test-server"

    @pytest.mark.asyncio
    async def test_call_tool_success(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(result={
            "content": [{"type": "text", "text": "hello world"}]
        })

        client = MCPClient(_server_config(), transport)
        await client.connect()
        result = await client.call_tool("read", {"path": "/tmp/x"})

        assert result["content"][0]["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_call_tool_error(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(error={"code": -1, "message": "not found"})

        client = MCPClient(_server_config(), transport)
        await client.connect()
        with pytest.raises(RuntimeError, match="not found"):
            await client.call_tool("read", {"path": "/nope"})

    @pytest.mark.asyncio
    async def test_list_resources_no_capability(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})

        client = MCPClient(_server_config(), transport)
        await client.connect()
        resources = await client.list_resources()
        assert resources == []

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})

        client = MCPClient(_server_config(), transport)
        await client.connect()
        await client.close()

        assert not client.is_initialized
        assert not transport.is_connected


# --- bridge ---


class TestMCPToolBridge:
    def _make_bridge(self) -> tuple[MCPToolBridge, MCPClient, MockTransport]:
        transport = MockTransport()
        transport._connected = True
        client = MCPClient(_server_config(), transport)
        client._initialized = True
        bridge = MCPToolBridge(_tool_def(), client)
        return bridge, client, transport

    def test_name_format(self) -> None:
        bridge, _, _ = self._make_bridge()
        assert bridge.name == "mcp.test-server.read_file"

    def test_description(self) -> None:
        bridge, _, _ = self._make_bridge()
        assert bridge.description == "Read a file"

    def test_parameters_schema(self) -> None:
        bridge, _, _ = self._make_bridge()
        schema = bridge.parameters_schema
        assert schema["type"] == "object"
        assert "path" in schema["properties"]

    def test_required_capability(self) -> None:
        bridge, _, _ = self._make_bridge()
        assert bridge.required_capability == "tool.mcp.test-server"

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        bridge, _, transport = self._make_bridge()
        transport.queue_response(result={
            "content": [{"type": "text", "text": "file contents here"}]
        })

        result = await bridge.execute(path="/tmp/test.txt")
        assert result.success
        assert "file contents here" in result.output

    @pytest.mark.asyncio
    async def test_execute_error_result(self) -> None:
        bridge, _, transport = self._make_bridge()
        transport.queue_response(result={
            "content": [{"type": "text", "text": "permission denied"}],
            "isError": True,
        })

        result = await bridge.execute(path="/root/secret")
        assert not result.success
        assert "permission denied" in result.error

    @pytest.mark.asyncio
    async def test_execute_not_connected(self) -> None:
        bridge, client, _ = self._make_bridge()
        client._initialized = False

        result = await bridge.execute(path="/tmp/x")
        assert not result.success
        assert "not connected" in result.error

    @pytest.mark.asyncio
    async def test_execute_image_content(self) -> None:
        bridge, _, transport = self._make_bridge()
        transport.queue_response(result={
            "content": [
                {"type": "image", "data": "base64data", "mimeType": "image/png"},
            ]
        })

        result = await bridge.execute(path="/tmp/img.png")
        assert result.success
        assert result.data["image"] == "base64data"
        assert "[image data]" in result.output


# --- manager ---


class TestMCPManager:
    @pytest.mark.asyncio
    async def test_connect_server(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        transport = MockTransport()
        transport.queue_response(result={
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock", "version": "1.0"},
        })
        transport.queue_response(result={})
        transport.queue_response(result={
            "tools": [
                {"name": "tool_a", "description": "A", "inputSchema": {}},
                {"name": "tool_b", "description": "B", "inputSchema": {}},
            ]
        })

        with patch("tars.mcp.manager.MCPManager._create_transport", return_value=transport):
            count = await manager.connect_server(_server_config("mock"))

        assert count == 2
        assert "mcp.mock.tool_a" in registry
        assert "mcp.mock.tool_b" in registry
        assert manager.tool_count == 2
        assert "mock" in manager.connected_servers

        await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_disconnect_server(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(result={
            "tools": [{"name": "x", "description": "X", "inputSchema": {}}]
        })

        with patch("tars.mcp.manager.MCPManager._create_transport", return_value=transport):
            await manager.connect_server(_server_config("srv"))

        assert "mcp.srv.x" in registry
        await manager.disconnect_server("srv")
        assert "mcp.srv.x" not in registry
        assert manager.tool_count == 0

    @pytest.mark.asyncio
    async def test_connect_duplicate_skipped(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(result={"tools": []})

        with patch("tars.mcp.manager.MCPManager._create_transport", return_value=transport):
            await manager.connect_server(_server_config("dup"))
            count = await manager.connect_server(_server_config("dup"))

        assert count == 0

        await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_refresh_server(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        transport = MockTransport()
        transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(result={
            "tools": [{"name": "old", "description": "Old", "inputSchema": {}}]
        })

        with patch("tars.mcp.manager.MCPManager._create_transport", return_value=transport):
            await manager.connect_server(_server_config("ref"))

        assert "mcp.ref.old" in registry

        transport.queue_response(result={
            "tools": [
                {"name": "new1", "description": "New1", "inputSchema": {}},
                {"name": "new2", "description": "New2", "inputSchema": {}},
            ]
        })

        count = await manager.refresh_server("ref")
        assert count == 2
        assert "mcp.ref.old" not in registry
        assert "mcp.ref.new1" in registry
        assert "mcp.ref.new2" in registry

        await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_get_server_info(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        transport = MockTransport()
        transport.queue_response(result={"capabilities": {"tools": {}}, "serverInfo": {}})
        transport.queue_response(result={})
        transport.queue_response(result={
            "tools": [{"name": "t1", "description": "T", "inputSchema": {}}]
        })

        with patch("tars.mcp.manager.MCPManager._create_transport", return_value=transport):
            await manager.connect_server(_server_config("info"))

        info = manager.get_server_info()
        assert len(info) == 1
        assert info[0]["name"] == "info"
        assert info[0]["initialized"]
        assert "mcp.info.t1" in info[0]["tools"]

        await manager.disconnect_all()

    @pytest.mark.asyncio
    async def test_connect_all_with_failure(self) -> None:
        registry = ToolRegistry()
        manager = MCPManager(registry)

        good_transport = MockTransport()
        good_transport.queue_response(result={"capabilities": {}, "serverInfo": {}})
        good_transport.queue_response(result={})
        good_transport.queue_response(result={"tools": []})

        bad_transport = MockTransport()
        bad_transport.queue_response(error={"code": -1, "message": "nope"})

        call_count = 0

        def fake_transport(config: MCPServerConfig) -> MockTransport:
            nonlocal call_count
            call_count += 1
            if config.name == "bad":
                return bad_transport
            return good_transport

        with patch.object(manager, "_create_transport", side_effect=fake_transport):
            results = await manager.connect_all([
                _server_config("good"),
                _server_config("bad"),
            ])

        assert results["good"] == 0
        assert isinstance(results["bad"], str)
        assert "error" in results["bad"]

        await manager.disconnect_all()


# --- config ---


class TestMCPConfig:
    def test_default_empty(self) -> None:
        from tars.core.config import TarsConfig

        cfg = TarsConfig()
        assert cfg.mcp.servers == {}

    def test_mcp_server_entry(self) -> None:
        from tars.core.config import MCPConfig, MCPServerEntry

        entry = MCPServerEntry(
            transport="stdio",
            command=["npx", "-y", "@modelcontextprotocol/server-filesystem"],
            args=["/home/user"],
        )
        config = MCPConfig(servers={"fs": entry})
        assert config.servers["fs"].transport == "stdio"
        assert len(config.servers["fs"].command) == 3

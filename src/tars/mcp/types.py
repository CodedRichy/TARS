from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TransportType(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


@dataclass
class MCPServerConfig:
    name: str
    transport: TransportType
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    oauth_client_id: str = ""
    oauth_scopes: list[str] = field(default_factory=list)


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPResourceDefinition:
    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    server_name: str = ""


@dataclass
class MCPPromptDefinition:
    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)
    server_name: str = ""


JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass
class JSONRPCRequest:
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: int | str = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": self.id,
            "method": self.method,
            "params": self.params,
        }


@dataclass
class JSONRPCResponse:
    id: int | str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JSONRPCResponse:
        return cls(
            id=data.get("id", 0),
            result=data.get("result"),
            error=data.get("error"),
        )

    @property
    def is_error(self) -> bool:
        return self.error is not None

from __future__ import annotations

from typing import Any

from tars.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def to_dict(self) -> dict[str, Tool]:
        return dict(self._tools)

    def to_schema_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
                "required_capability": t.required_capability,
            }
            for t in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_default_registry() -> ToolRegistry:
    from tars.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool
    from tars.tools.shell import ShellTool

    registry = ToolRegistry()
    registry.register(ShellTool())
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(ListFilesTool())
    return registry

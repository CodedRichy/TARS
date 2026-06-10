from __future__ import annotations

from tars.tools.base import Tool, ToolResult
from tars.tools.registry import ToolRegistry, create_default_registry


class DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A dummy tool for testing"

    async def execute(self, **kwargs: object) -> ToolResult:
        return ToolResult(success=True, output="ok")


def test_register_and_get() -> None:
    reg = ToolRegistry()
    tool = DummyTool()
    reg.register(tool)
    assert reg.get("dummy") is tool


def test_get_missing_returns_none() -> None:
    reg = ToolRegistry()
    assert reg.get("nonexistent") is None


def test_unregister() -> None:
    reg = ToolRegistry()
    reg.register(DummyTool())
    assert reg.unregister("dummy")
    assert reg.get("dummy") is None


def test_unregister_missing_returns_false() -> None:
    reg = ToolRegistry()
    assert not reg.unregister("nonexistent")


def test_list_all() -> None:
    reg = ToolRegistry()
    reg.register(DummyTool())
    tools = reg.list_all()
    assert len(tools) == 1
    assert tools[0].name == "dummy"


def test_names() -> None:
    reg = ToolRegistry()
    reg.register(DummyTool())
    assert reg.names() == ["dummy"]


def test_to_dict() -> None:
    reg = ToolRegistry()
    tool = DummyTool()
    reg.register(tool)
    d = reg.to_dict()
    assert d["dummy"] is tool


def test_to_schema_list() -> None:
    reg = ToolRegistry()
    reg.register(DummyTool())
    schemas = reg.to_schema_list()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "dummy"
    assert schemas[0]["description"] == "A dummy tool for testing"
    assert schemas[0]["required_capability"] == "tool.dummy"


def test_len_and_contains() -> None:
    reg = ToolRegistry()
    assert len(reg) == 0
    assert "dummy" not in reg
    reg.register(DummyTool())
    assert len(reg) == 1
    assert "dummy" in reg


def test_create_default_registry() -> None:
    reg = create_default_registry()
    assert "shell" in reg
    assert "read_file" in reg
    assert "write_file" in reg
    assert "list_files" in reg
    assert len(reg) == 4

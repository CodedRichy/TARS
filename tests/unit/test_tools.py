from __future__ import annotations

import platform
from pathlib import Path

import pytest

from tars.tools.base import ToolResult
from tars.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool
from tars.tools.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_echo() -> None:
    tool = ShellTool()
    if platform.system() == "Windows":
        result = await tool.execute(command="echo hello")
    else:
        result = await tool.execute(command="echo hello")
    assert result.success
    assert "hello" in result.output


@pytest.mark.asyncio
async def test_shell_empty_command() -> None:
    tool = ShellTool()
    result = await tool.execute(command="")
    assert not result.success
    assert "Empty" in result.error


@pytest.mark.asyncio
async def test_shell_blocked_command() -> None:
    tool = ShellTool()
    result = await tool.execute(command="rm -rf /")
    assert not result.success
    assert "Blocked" in result.error


@pytest.mark.asyncio
async def test_read_file(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    tool = ReadFileTool()
    result = await tool.execute(path=str(f))
    assert result.success
    assert result.output == "hello world"


@pytest.mark.asyncio
async def test_read_file_not_found() -> None:
    tool = ReadFileTool()
    result = await tool.execute(path="/nonexistent/file.txt")
    assert not result.success
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_read_file_path_restriction(tmp_path: Path) -> None:
    f = tmp_path / "test.txt"
    f.write_text("secret")
    tool = ReadFileTool(allowed_roots=[Path("/some/other/root")])
    result = await tool.execute(path=str(f))
    assert not result.success
    assert "outside" in result.error.lower()


@pytest.mark.asyncio
async def test_write_file(tmp_path: Path) -> None:
    f = tmp_path / "output.txt"
    tool = WriteFileTool()
    result = await tool.execute(path=str(f), content="written content")
    assert result.success
    assert f.read_text() == "written content"


@pytest.mark.asyncio
async def test_write_creates_dirs(tmp_path: Path) -> None:
    f = tmp_path / "sub" / "dir" / "file.txt"
    tool = WriteFileTool()
    result = await tool.execute(path=str(f), content="nested")
    assert result.success
    assert f.read_text() == "nested"


@pytest.mark.asyncio
async def test_list_files(tmp_path: Path) -> None:
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.txt").touch()
    (tmp_path / "subdir").mkdir()
    tool = ListFilesTool()
    result = await tool.execute(path=str(tmp_path))
    assert result.success
    assert "a.txt" in result.output
    assert "b.txt" in result.output


@pytest.mark.asyncio
async def test_list_files_not_found() -> None:
    tool = ListFilesTool()
    result = await tool.execute(path="/nonexistent/dir")
    assert not result.success


def test_tool_result_defaults() -> None:
    r = ToolResult(success=True)
    assert r.output == ""
    assert r.error == ""
    assert r.data == {}

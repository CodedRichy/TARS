from __future__ import annotations

import json
from pathlib import Path

import pytest

from tars.tools.calendar import CalendarTool
from tars.tools.code_analysis import CodeAnalysisTool
from tars.tools.database import DatabaseTool
from tars.tools.docker import DockerTool
from tars.tools.git import GitTool
from tars.tools.ssh_tool import SSHTool
from tars.tools.web_search import WebSearchTool

# --- Git Tool ---


@pytest.mark.asyncio
async def test_git_status() -> None:
    tool = GitTool()
    result = await tool.execute(subcommand="status")
    assert isinstance(result.output, str)


@pytest.mark.asyncio
async def test_git_blocked_subcommand() -> None:
    tool = GitTool()
    result = await tool.execute(subcommand="filter-branch")
    assert not result.success
    assert "not allowed" in result.error


@pytest.mark.asyncio
async def test_git_log() -> None:
    tool = GitTool()
    result = await tool.execute(subcommand="log", args=["--oneline", "-5"])
    assert isinstance(result.output, str)


# --- Code Analysis Tool ---


@pytest.mark.asyncio
async def test_code_analysis_file(tmp_path: Path) -> None:
    py_file = tmp_path / "example.py"
    py_file.write_text(
        "import os\n\ndef hello(name: str) -> str:\n    return f'Hello {name}'\n\n"
        "class Greeter:\n    def greet(self):\n        pass\n"
    )
    tool = CodeAnalysisTool()
    result = await tool.execute(path=str(py_file), mode="all")
    assert result.success
    data = json.loads(result.output)
    assert len(data["functions"]) == 1
    assert data["functions"][0]["name"] == "hello"
    assert len(data["classes"]) == 1
    assert data["classes"][0]["name"] == "Greeter"
    assert any(i.get("module") == "os" for i in data["imports"])


@pytest.mark.asyncio
async def test_code_analysis_not_python(tmp_path: Path) -> None:
    txt = tmp_path / "readme.txt"
    txt.write_text("hello")
    tool = CodeAnalysisTool()
    result = await tool.execute(path=str(txt))
    assert not result.success
    assert "Not a Python file" in result.error


@pytest.mark.asyncio
async def test_code_analysis_directory(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("def foo(): pass\n")
    tool = CodeAnalysisTool()
    result = await tool.execute(path=str(tmp_path), mode="structure")
    assert result.success
    data = json.loads(result.output)
    assert data["python_files"] == 2


@pytest.mark.asyncio
async def test_code_analysis_missing_path() -> None:
    tool = CodeAnalysisTool()
    result = await tool.execute(path="/nonexistent/file.py")
    assert not result.success


# --- Database Tool ---


@pytest.mark.asyncio
async def test_database_schema(tmp_path: Path) -> None:
    import aiosqlite

    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        await db.commit()

    tool = DatabaseTool()
    result = await tool.execute(path=str(db_path), mode="schema")
    assert result.success
    data = json.loads(result.output)
    assert any(t["name"] == "users" for t in data)


@pytest.mark.asyncio
async def test_database_query(tmp_path: Path) -> None:
    import aiosqlite

    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)")
        await db.execute("INSERT INTO items (val) VALUES ('alpha')")
        await db.execute("INSERT INTO items (val) VALUES ('beta')")
        await db.commit()

    tool = DatabaseTool()
    result = await tool.execute(path=str(db_path), query="SELECT * FROM items")
    assert result.success
    assert result.data["row_count"] == 2
    parsed = json.loads(result.output)
    assert len(parsed["rows"]) == 2


@pytest.mark.asyncio
async def test_database_blocked_query(tmp_path: Path) -> None:
    import aiosqlite

    db_path = tmp_path / "test.db"
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("CREATE TABLE t (id INTEGER)")
        await db.commit()

    tool = DatabaseTool()
    result = await tool.execute(path=str(db_path), query="DROP TABLE t")
    assert not result.success
    assert "Blocked" in result.error


@pytest.mark.asyncio
async def test_database_missing_file() -> None:
    tool = DatabaseTool()
    result = await tool.execute(path="/no/such/db.sqlite")
    assert not result.success


# --- Docker Tool ---


def test_docker_tool_properties() -> None:
    tool = DockerTool()
    assert tool.name == "docker"
    assert tool.required_capability == "tool.docker"


@pytest.mark.asyncio
async def test_docker_blocked_subcommand() -> None:
    tool = DockerTool()
    result = await tool.execute(subcommand="system")
    assert not result.success
    assert "not allowed" in result.error


@pytest.mark.asyncio
async def test_docker_blocked_flag() -> None:
    tool = DockerTool()
    result = await tool.execute(subcommand="run", args=["--privileged", "alpine"])
    assert not result.success
    assert "Blocked flag" in result.error


# --- Web Search Tool ---


def test_web_search_properties() -> None:
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert "query" in tool.parameters_schema["properties"]


@pytest.mark.asyncio
async def test_web_search_empty_query() -> None:
    tool = WebSearchTool()
    result = await tool.execute(query="")
    assert not result.success
    assert "Empty query" in result.error


# --- SSH Tool ---


def test_ssh_tool_properties() -> None:
    tool = SSHTool()
    assert tool.name == "ssh"
    assert tool.required_capability == "tool.ssh"


@pytest.mark.asyncio
async def test_ssh_missing_params() -> None:
    tool = SSHTool()
    result = await tool.execute(host="", command="")
    assert not result.success
    assert "required" in result.error


# --- Calendar Tool ---


@pytest.mark.asyncio
async def test_calendar_create(tmp_path: Path) -> None:
    tool = CalendarTool()
    ics_path = str(tmp_path / "meeting.ics")
    result = await tool.execute(
        action="create",
        title="Standup",
        start="2026-06-06T10:00:00",
        duration_minutes=30,
        path=ics_path,
    )
    assert result.success
    assert Path(ics_path).exists()

    content = Path(ics_path).read_text()
    assert "Standup" in content
    assert "BEGIN:VEVENT" in content


@pytest.mark.asyncio
async def test_calendar_read(tmp_path: Path) -> None:
    tool = CalendarTool()
    ics_path = str(tmp_path / "test.ics")
    await tool.execute(
        action="create",
        title="Review",
        start="2026-06-07T14:00:00",
        path=ics_path,
    )

    result = await tool.execute(action="read", path=ics_path)
    assert result.success
    events = json.loads(result.output)
    assert len(events) == 1
    assert events[0]["title"] == "Review"


@pytest.mark.asyncio
async def test_calendar_list(tmp_path: Path) -> None:
    tool = CalendarTool()
    (tmp_path / "a.ics").write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    (tmp_path / "b.ics").write_text("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")

    result = await tool.execute(action="list", path=str(tmp_path))
    assert result.success
    files = json.loads(result.output)
    assert len(files) == 2


@pytest.mark.asyncio
async def test_calendar_create_missing_title() -> None:
    tool = CalendarTool()
    result = await tool.execute(action="create", start="2026-06-06T10:00:00")
    assert not result.success
    assert "required" in result.error

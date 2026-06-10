from __future__ import annotations

from pathlib import Path
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_READ_CHARS = 100_000
MAX_WRITE_CHARS = 500_000


class ReadFileTool(Tool):
    def __init__(self, allowed_roots: list[Path] | None = None) -> None:
        self._allowed_roots = allowed_roots or []

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read a file and return its contents."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
            },
            "required": ["path"],
        }

    def _check_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        if self._allowed_roots and not any(
            self._is_under(resolved, root) for root in self._allowed_roots
        ):
            return f"Path outside allowed roots: {resolved}"
        return None

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root.resolve())
            return True
        except ValueError:
            return False

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", "")
        if not raw_path:
            return ToolResult(success=False, error="No path specified")

        path = Path(raw_path)
        if err := self._check_path(path):
            return ToolResult(success=False, error=err)

        if not path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        if path.is_dir():
            items = sorted(p.name for p in path.iterdir())
            return ToolResult(success=True, output="\n".join(items))

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if len(content) > MAX_READ_CHARS:
                content = content[:MAX_READ_CHARS] + "\n... [truncated]"
            return ToolResult(success=True, output=content)
        except OSError as e:
            return ToolResult(success=False, error=str(e))


class WriteFileTool(Tool):
    def __init__(self, allowed_roots: list[Path] | None = None) -> None:
        self._allowed_roots = allowed_roots or []

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file, creating parent directories as needed."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", "")
        content = kwargs.get("content", "")

        if not raw_path:
            return ToolResult(success=False, error="No path specified")

        if len(content) > MAX_WRITE_CHARS:
            return ToolResult(
                success=False,
                error=f"Content too large: {len(content)} chars (max {MAX_WRITE_CHARS})",
            )

        path = Path(raw_path)
        if self._allowed_roots:
            resolved = path.resolve()
            if not any(ReadFileTool._is_under(resolved, r) for r in self._allowed_roots):
                return ToolResult(success=False, error=f"Path outside allowed roots: {resolved}")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Wrote {len(content)} chars to {path}",
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e))


class ListFilesTool(Tool):
    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List files and directories at a path."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively",
                    "default": False,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)

        path = Path(raw_path)
        if not path.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")
        if not path.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")

        try:
            if recursive:
                items = sorted(str(p.relative_to(path)) for p in path.rglob("*") if p.is_file())
            else:
                items = sorted(f"{'[dir] ' if p.is_dir() else ''}{p.name}" for p in path.iterdir())
            return ToolResult(success=True, output="\n".join(items[:500]))
        except OSError as e:
            return ToolResult(success=False, error=str(e))

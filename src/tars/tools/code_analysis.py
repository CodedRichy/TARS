from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from tars.tools.base import Tool, ToolResult

MAX_FILE_SIZE = 500_000


class CodeAnalysisTool(Tool):
    @property
    def name(self) -> str:
        return "code_analysis"

    @property
    def description(self) -> str:
        return (
            "Analyze Python source code: extract functions, classes, imports, "
            "dependencies, and structure."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Python file or directory to analyze"},
                "mode": {
                    "type": "string",
                    "enum": ["structure", "imports", "functions", "classes", "all"],
                    "description": "What to extract",
                    "default": "all",
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", "")
        mode = kwargs.get("mode", "all")

        if not raw_path:
            return ToolResult(success=False, error="No path specified")

        path = Path(raw_path)
        if not path.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        if path.is_dir():
            return self._analyze_directory(path, mode)
        return self._analyze_file(path, mode)

    def _analyze_file(self, path: Path, mode: str) -> ToolResult:
        if path.suffix != ".py":
            return ToolResult(success=False, error=f"Not a Python file: {path}")

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ToolResult(success=False, error=str(e))

        if len(source) > MAX_FILE_SIZE:
            return ToolResult(success=False, error=f"File too large: {len(source)} bytes")

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            return ToolResult(success=False, error=f"Syntax error: {e}")

        result: dict[str, Any] = {"file": str(path)}

        if mode in ("imports", "all"):
            result["imports"] = self._extract_imports(tree)

        if mode in ("functions", "all"):
            result["functions"] = self._extract_functions(tree)

        if mode in ("classes", "all"):
            result["classes"] = self._extract_classes(tree)

        if mode in ("structure", "all"):
            result["structure"] = {
                "lines": len(source.splitlines()),
                "top_level_nodes": len(tree.body),
            }

        return ToolResult(
            success=True,
            output=json.dumps(result, indent=2),
            data=result,
        )

    def _analyze_directory(self, path: Path, mode: str) -> ToolResult:
        py_files = sorted(path.rglob("*.py"))
        if not py_files:
            return ToolResult(success=False, error=f"No Python files in {path}")

        summary: dict[str, Any] = {
            "directory": str(path),
            "python_files": len(py_files),
            "files": [],
        }

        for f in py_files[:50]:
            try:
                source = f.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(f))
                info: dict[str, Any] = {
                    "path": str(f.relative_to(path)),
                    "lines": len(source.splitlines()),
                    "functions": len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]),
                    "classes": len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]),
                }
                summary["files"].append(info)
            except (SyntaxError, OSError):
                summary["files"].append({"path": str(f.relative_to(path)), "error": "parse failed"})

        return ToolResult(
            success=True,
            output=json.dumps(summary, indent=2),
            data=summary,
        )

    @staticmethod
    def _extract_imports(tree: ast.Module) -> list[dict[str, Any]]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"module": alias.name, "alias": alias.asname})
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({
                        "from": module,
                        "name": alias.name,
                        "alias": alias.asname,
                    })
        return imports

    @staticmethod
    def _extract_functions(tree: ast.Module) -> list[dict[str, Any]]:
        functions = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append({
                    "name": node.name,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "args": [a.arg for a in node.args.args],
                    "decorators": [ast.dump(d) for d in node.decorator_list],
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                })
        return functions

    @staticmethod
    def _extract_classes(tree: ast.Module) -> list[dict[str, Any]]:
        classes = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name
                    for n in ast.iter_child_nodes(node)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.dump(base))
                classes.append({
                    "name": node.name,
                    "bases": bases,
                    "methods": methods,
                    "line": node.lineno,
                    "docstring": ast.get_docstring(node) or "",
                })
        return classes

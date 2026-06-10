from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from tars.tools.base import Tool, ToolResult

MAX_ROWS = 500
MAX_OUTPUT = 50_000

BLOCKED_KEYWORDS = frozenset({
    "DROP DATABASE", "DROP TABLE", "TRUNCATE", "ALTER TABLE",
    "CREATE DATABASE", "GRANT", "REVOKE",
})


class DatabaseTool(Tool):
    @property
    def name(self) -> str:
        return "database"

    @property
    def description(self) -> str:
        return "Query SQLite databases: run SELECT queries and inspect schema."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to SQLite database file"},
                "query": {"type": "string", "description": "SQL query to execute"},
                "mode": {
                    "type": "string",
                    "enum": ["query", "schema"],
                    "description": "Mode: 'query' to run SQL, 'schema' to inspect tables",
                    "default": "query",
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw_path = kwargs.get("path", "")
        mode = kwargs.get("mode", "query")
        query = kwargs.get("query", "")

        if not raw_path:
            return ToolResult(success=False, error="No database path specified")

        db_path = Path(raw_path)
        if not db_path.exists():
            return ToolResult(success=False, error=f"Database not found: {db_path}")

        if mode == "schema":
            return await self._get_schema(db_path)

        if not query.strip():
            return ToolResult(success=False, error="No query specified")

        upper = query.upper().strip()
        for blocked in BLOCKED_KEYWORDS:
            if blocked in upper:
                return ToolResult(success=False, error=f"Blocked operation: {blocked}")

        return await self._run_query(db_path, query)

    async def _get_schema(self, db_path: Path) -> ToolResult:
        try:
            async with aiosqlite.connect(str(db_path)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = await cursor.fetchall()

                schema = []
                for table in tables:
                    schema.append({
                        "name": table["name"],
                        "sql": table["sql"],
                    })

                return ToolResult(
                    success=True,
                    output=json.dumps(schema, indent=2),
                    data={"table_count": len(schema)},
                )
        except Exception as e:
            return ToolResult(success=False, error=f"Schema inspection failed: {e}")

    async def _run_query(self, db_path: Path, query: str) -> ToolResult:
        try:
            async with aiosqlite.connect(str(db_path)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query)
                rows = await cursor.fetchmany(MAX_ROWS)

                if not rows:
                    return ToolResult(
                        success=True,
                        output="Query returned no rows",
                        data={"row_count": 0},
                    )

                columns = list(rows[0].keys())
                result_rows = [dict(row) for row in rows]

                output = json.dumps(
                    {"columns": columns, "rows": result_rows},
                    indent=2,
                    default=str,
                )[:MAX_OUTPUT]

                return ToolResult(
                    success=True,
                    output=output,
                    data={"row_count": len(result_rows), "columns": columns},
                )
        except Exception as e:
            return ToolResult(success=False, error=f"Query failed: {e}")

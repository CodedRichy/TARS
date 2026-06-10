from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tars.tools.base import Tool, ToolResult


class CalendarTool(Tool):
    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Create and read calendar events (ICS format)."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "read", "list"],
                    "description": "Calendar action",
                },
                "path": {
                    "type": "string",
                    "description": "Path to .ics file",
                },
                "title": {"type": "string", "description": "Event title"},
                "start": {
                    "type": "string",
                    "description": "Start time (ISO 8601)",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes",
                    "default": 60,
                },
                "description": {"type": "string", "description": "Event description"},
                "location": {"type": "string", "description": "Event location"},
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "")

        if action == "create":
            return self._create_event(kwargs)
        if action == "read":
            return self._read_events(kwargs)
        if action == "list":
            return self._list_ics_files(kwargs)

        return ToolResult(success=False, error=f"Unknown action: {action}")

    def _create_event(self, kwargs: dict[str, Any]) -> ToolResult:
        title = kwargs.get("title", "")
        start_str = kwargs.get("start", "")
        duration = kwargs.get("duration_minutes", 60)
        description = kwargs.get("description", "")
        location = kwargs.get("location", "")
        path = kwargs.get("path", "event.ics")

        if not title or not start_str:
            return ToolResult(success=False, error="title and start are required")

        try:
            start = datetime.fromisoformat(start_str)
        except ValueError:
            return ToolResult(success=False, error=f"Invalid start time: {start_str}")

        end = start + timedelta(minutes=duration)

        uid = f"tars-{start.strftime('%Y%m%dT%H%M%S')}@tars.local"
        now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        ics = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//TARS//Agent//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:{uid}\r\n"
            f"DTSTAMP:{now}\r\n"
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}\r\n"
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}\r\n"
            f"SUMMARY:{title}\r\n"
        )
        if description:
            ics += f"DESCRIPTION:{description}\r\n"
        if location:
            ics += f"LOCATION:{location}\r\n"
        ics += "END:VEVENT\r\nEND:VCALENDAR\r\n"

        try:
            Path(path).write_text(ics, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Event created: {title} at {start.isoformat()}",
                data={"path": path, "uid": uid},
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e))

    def _read_events(self, kwargs: dict[str, Any]) -> ToolResult:
        path = kwargs.get("path", "")
        if not path:
            return ToolResult(success=False, error="path is required")

        p = Path(path)
        if not p.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        try:
            content = p.read_text(encoding="utf-8")
            events = self._parse_ics(content)
            return ToolResult(
                success=True,
                output=json.dumps(events, indent=2),
                data={"count": len(events)},
            )
        except OSError as e:
            return ToolResult(success=False, error=str(e))

    def _list_ics_files(self, kwargs: dict[str, Any]) -> ToolResult:
        path = kwargs.get("path", ".")
        p = Path(path)
        if not p.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")

        files = sorted(p.glob("*.ics"))
        return ToolResult(
            success=True,
            output=json.dumps([str(f) for f in files]),
            data={"count": len(files)},
        )

    @staticmethod
    def _parse_ics(content: str) -> list[dict[str, str]]:
        events = []
        current: dict[str, str] | None = None

        for line in content.splitlines():
            line = line.strip()
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT" and current is not None:
                events.append(current)
                current = None
            elif current is not None and ":" in line:
                key, _, value = line.partition(":")
                key_map = {
                    "SUMMARY": "title",
                    "DTSTART": "start",
                    "DTEND": "end",
                    "DESCRIPTION": "description",
                    "LOCATION": "location",
                    "UID": "uid",
                }
                if key in key_map:
                    current[key_map[key]] = value

        return events

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from tars.tools.base import Tool, ToolResult

MAX_RESPONSE_CHARS = 100_000
DEFAULT_TIMEOUT_S = 15


class WebFetchTool(Tool):
    def __init__(self, allowed_domains: list[str] | None = None) -> None:
        self._allowed_domains = allowed_domains

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch content from a URL via HTTP GET."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST"],
                    "default": "GET",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers",
                },
                "body": {"type": "string", "description": "Request body for POST"},
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET")
        headers = kwargs.get("headers", {})
        body = kwargs.get("body")

        if not url:
            return ToolResult(success=False, error="No URL specified")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(success=False, error=f"Invalid scheme: {parsed.scheme}")

        if self._allowed_domains and parsed.hostname not in self._allowed_domains:
            return ToolResult(
                success=False,
                error=f"Domain not allowed: {parsed.hostname}",
            )

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
                if method == "POST":
                    resp = await client.post(url, headers=headers, content=body)
                else:
                    resp = await client.get(url, headers=headers)

                text = resp.text[:MAX_RESPONSE_CHARS]
                return ToolResult(
                    success=resp.is_success,
                    output=text,
                    data={
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                    },
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error="Request timed out")
        except httpx.HTTPError as e:
            return ToolResult(success=False, error=str(e))

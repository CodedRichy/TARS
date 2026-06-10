from __future__ import annotations

import json
from typing import Any

import httpx

from tars.tools.base import Tool, ToolResult

TIMEOUT_S = 15
MAX_RESULTS = 10


class WebSearchTool(Tool):
    def __init__(
        self,
        *,
        searxng_url: str = "http://localhost:8888",
        brave_api_key: str = "",
    ) -> None:
        self._searxng_url = searxng_url.rstrip("/")
        self._brave_api_key = brave_api_key

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return structured results. Uses SearXNG or Brave Search."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": MAX_RESULTS,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", MAX_RESULTS)

        if not query.strip():
            return ToolResult(success=False, error="Empty query")

        if self._brave_api_key:
            return await self._brave_search(query, max_results)
        return await self._searxng_search(query, max_results)

    async def _searxng_search(self, query: str, max_results: int) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                resp = await client.get(
                    f"{self._searxng_url}/search",
                    params={"q": query, "format": "json", "pageno": 1},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                })

            return ToolResult(
                success=True,
                output=json.dumps(results, indent=2),
                data={"count": len(results), "engine": "searxng"},
            )
        except httpx.ConnectError:
            return ToolResult(
                success=False,
                error=f"Cannot connect to SearXNG at {self._searxng_url}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"SearXNG error: {e}")

    async def _brave_search(self, query: str, max_results: int) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": max_results},
                    headers={
                        "X-Subscription-Token": self._brave_api_key,
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("web", {}).get("results", [])[:max_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                })

            return ToolResult(
                success=True,
                output=json.dumps(results, indent=2),
                data={"count": len(results), "engine": "brave"},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Brave Search error: {e}")

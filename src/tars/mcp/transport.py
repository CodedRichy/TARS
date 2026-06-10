from __future__ import annotations

import asyncio
import contextlib
import json
import os
from abc import ABC, abstractmethod
from typing import Any

from tars.core.log import get_logger
from tars.mcp.types import JSONRPCRequest, JSONRPCResponse

logger = get_logger("mcp.transport")


class MCPTransport(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse: ...

    @abstractmethod
    async def close(self) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...


class StdioTransport(MCPTransport):
    def __init__(
        self,
        command: list[str],
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._command = command
        self._args = args or []
        self._env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int | str, asyncio.Future[JSONRPCResponse]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self) -> None:
        merged_env = {**os.environ, **self._env}
        cmd = self._command + self._args
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        logger.info("stdio transport started: %s", " ".join(cmd))

    async def _read_loop(self) -> None:
        assert self._process and self._process.stdout
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line.decode("utf-8").strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            if "id" in data and data["id"] in self._pending:
                resp = JSONRPCResponse.from_dict(data)
                fut = self._pending.pop(data["id"])
                if not fut.done():
                    fut.set_result(resp)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self.is_connected:
            raise ConnectionError("stdio transport not connected")

        assert self._process and self._process.stdin
        self._request_id += 1
        request.id = self._request_id

        fut: asyncio.Future[JSONRPCResponse] = asyncio.get_event_loop().create_future()
        self._pending[request.id] = fut

        payload = json.dumps(request.to_dict()) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=30.0)
        except TimeoutError:
            self._pending.pop(request.id, None)
            raise TimeoutError(f"MCP request timed out: {request.method}") from None

    async def close(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (TimeoutError, ProcessLookupError):
                self._process.kill()
            self._process = None

        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        logger.info("stdio transport closed")


class HttpTransport(MCPTransport):
    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._headers = headers or {}
        self._client: Any = None
        self._request_id = 0

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def start(self) -> None:
        import httpx

        self._client = httpx.AsyncClient(
            base_url=self._url,
            headers={
                "Content-Type": "application/json",
                **self._headers,
            },
            timeout=30.0,
        )
        logger.info("HTTP transport started: %s", self._url)

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._client:
            raise ConnectionError("HTTP transport not connected")

        self._request_id += 1
        request.id = self._request_id

        resp = await self._client.post("/", json=request.to_dict())
        resp.raise_for_status()
        data = resp.json()
        return JSONRPCResponse.from_dict(data)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("HTTP transport closed")

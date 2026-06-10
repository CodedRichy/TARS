from __future__ import annotations

import asyncio
from typing import Any

from tars.channels.base import Channel


class CLIChannel(Channel):
    def __init__(self, prompt: str = "you> ") -> None:
        self._prompt = prompt
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def name(self) -> str:
        return "cli"

    async def send(self, message: str, **kwargs: Any) -> None:
        prefix = kwargs.get("prefix", "tars")
        print(f"[{prefix}] {message}")

    async def receive(self) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            line = await loop.run_in_executor(None, lambda: input(self._prompt))
            return line.strip() if line.strip() else None
        except (EOFError, KeyboardInterrupt):
            return None

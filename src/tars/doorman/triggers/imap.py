from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

logger = logging.getLogger("tars.doorman.imap")


@dataclass
class ImapTrigger:
    host: str
    username: str
    password: str
    folder: str = "INBOX"
    task_goal: str = "process new email"
    domain: str = "email"
    tags: list[str] | None = None


class ImapWatcher:
    def __init__(self) -> None:
        self._trigger: ImapTrigger | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def set_trigger(self, trigger: ImapTrigger) -> None:
        self._trigger = trigger

    async def start(self, callback) -> None:
        if not self._trigger:
            return
        self._running = True
        self._task = asyncio.create_task(self._idle_loop(callback))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _idle_loop(self, callback) -> None:
        trigger = self._trigger
        if not trigger:
            return

        while self._running:
            try:
                import imapclient

                loop = asyncio.get_running_loop()
                client = await loop.run_in_executor(
                    None, lambda: imapclient.IMAPClient(trigger.host, ssl=True)
                )
                await loop.run_in_executor(
                    None, lambda c=client: c.login(trigger.username, trigger.password)
                )
                await loop.run_in_executor(None, lambda c=client: c.select_folder(trigger.folder))

                logger.info("IMAP IDLE started on %s", trigger.host)

                while self._running:
                    responses = await loop.run_in_executor(
                        None, lambda c=client: c.idle_check(timeout=300)
                    )
                    if responses:
                        await loop.run_in_executor(None, client.idle_done)
                        await callback(trigger, responses)
                        await loop.run_in_executor(None, client.idle)

            except Exception:
                logger.exception("IMAP watcher error, retrying in 60s")
                await asyncio.sleep(60)

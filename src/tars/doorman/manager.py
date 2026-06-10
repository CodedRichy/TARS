from __future__ import annotations

import logging
from typing import Any

from tars.core.config import TarsConfig
from tars.doorman.triggers.cron import CronScheduler, CronTrigger
from tars.doorman.triggers.file_watch import FileWatcher, FileWatchTrigger

logger = logging.getLogger("tars.doorman")


class DoormanManager:
    def __init__(self, config: TarsConfig) -> None:
        self.config = config
        self.cron = CronScheduler()
        self.file_watcher = FileWatcher()
        self._callback: Any = None

    def setup_from_config(self) -> None:
        for expr in self.config.doorman.cron_triggers:
            parts = expr.split("|", 1)
            cron_expr = parts[0].strip()
            goal = parts[1].strip() if len(parts) > 1 else "scheduled task"
            self.cron.add_trigger(CronTrigger(expression=cron_expr, task_goal=goal))

        for path in self.config.doorman.file_watch_paths:
            parts = path.split("|", 1)
            watch_path = parts[0].strip()
            goal = parts[1].strip() if len(parts) > 1 else f"file changed: {watch_path}"
            self.file_watcher.add_trigger(FileWatchTrigger(path=watch_path, task_goal=goal))

    async def start(self, on_trigger) -> None:
        self._callback = on_trigger
        self.setup_from_config()

        if self.cron.trigger_count > 0:
            await self.cron.start(self._on_cron)
            logger.info("Cron scheduler started (%d triggers)", self.cron.trigger_count)

        if self.file_watcher.trigger_count > 0:
            await self.file_watcher.start(self._on_file)
            logger.info("File watcher started (%d watches)", self.file_watcher.trigger_count)

    async def stop(self) -> None:
        await self.cron.stop()
        await self.file_watcher.stop()

    async def _on_cron(self, trigger: CronTrigger) -> None:
        logger.info("Cron fired: %s -> %s", trigger.expression, trigger.task_goal)
        if self._callback:
            await self._callback(
                source="cron",
                goal=trigger.task_goal,
                domain=trigger.domain,
                tags=trigger.tags,
            )

    async def _on_file(self, trigger: FileWatchTrigger, path: str) -> None:
        logger.info("File changed: %s -> %s", path, trigger.task_goal)
        if self._callback:
            await self._callback(
                source="file_watch",
                goal=f"{trigger.task_goal} (changed: {path})",
                domain=trigger.domain,
                tags=trigger.tags,
            )

    @property
    def total_triggers(self) -> int:
        return self.cron.trigger_count + self.file_watcher.trigger_count

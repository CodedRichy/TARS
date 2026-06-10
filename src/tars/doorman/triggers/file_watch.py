from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


@dataclass
class FileWatchTrigger:
    path: str
    task_goal: str
    patterns: list[str] = field(default_factory=lambda: ["*"])
    domain: str = ""
    tags: list[str] | None = None


class _AsyncHandler(FileSystemEventHandler):
    def __init__(self, callback, loop: asyncio.AbstractEventLoop) -> None:
        self._callback = callback
        self._loop = loop

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            asyncio.run_coroutine_threadsafe(self._callback(event.src_path), self._loop)


class FileWatcher:
    def __init__(self) -> None:
        self._triggers: list[FileWatchTrigger] = []
        self._observer: Observer | None = None

    def add_trigger(self, trigger: FileWatchTrigger) -> None:
        self._triggers.append(trigger)

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)

    async def start(self, callback) -> None:
        if not self._triggers:
            return

        loop = asyncio.get_running_loop()
        self._observer = Observer()

        for trigger in self._triggers:
            path = Path(trigger.path)
            if not path.exists():
                continue
            watch_path = str(path if path.is_dir() else path.parent)
            handler = _AsyncHandler(lambda p, t=trigger: callback(t, p), loop)
            self._observer.schedule(handler, watch_path, recursive=False)

        self._observer.start()

    async def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)

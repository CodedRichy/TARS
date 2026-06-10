from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Channel(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send(self, message: str, **kwargs: Any) -> None: ...

    @abstractmethod
    async def receive(self) -> str | None: ...

    async def start(self) -> None:  # noqa: B027
        pass

    async def stop(self) -> None:  # noqa: B027
        pass

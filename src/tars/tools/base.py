from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str = ""
    data: dict = field(default_factory=dict)


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def parameters_schema(self) -> dict:
        return {}

    @property
    def required_capability(self) -> str:
        return f"tool.{self.name}"

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult: ...

    def validate_params(self, kwargs: dict) -> str | None:
        schema = self.parameters_schema
        required = schema.get("required", [])
        for key in required:
            if key not in kwargs:
                return f"Missing required parameter: {key}"
        return None

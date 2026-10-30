"""One tool registry for agents: each tool has a Pydantic parameter model and a handler."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ToolOutput:
    text: str


@dataclass(frozen=True)
class Tool[P: BaseModel]:
    name: str
    description: str
    params: type[P]
    run: Callable[[P], ToolOutput]

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.params.model_json_schema(),
            },
        }

    def call(self, arguments: str) -> ToolOutput:
        try:
            parsed = self.params.model_validate(json.loads(arguments or "{}"))
        except (json.JSONDecodeError, ValidationError) as exc:
            return ToolOutput(text=f"error: bad arguments for {self.name}: {exc}")
        return self.run(parsed)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any]] = {}

    def add(self, tool: Tool[Any]) -> ToolRegistry:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool
        return self

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    def call(self, name: str, arguments: str) -> ToolOutput:
        tool = self._tools.get(name)
        if tool is None:
            return ToolOutput(text=f"error: unknown tool {name!r}; use one of {self.names()}")
        try:
            return tool.call(arguments)
        except Exception as exc:  # the agent sees the failure and can recover
            return ToolOutput(text=f"error: {name} failed: {exc}")

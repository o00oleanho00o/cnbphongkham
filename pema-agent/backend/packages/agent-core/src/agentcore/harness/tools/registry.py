"""The tools an agent may call, by name."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agentcore.harness.model.types import ToolSchema
from agentcore.harness.tools.spec import ToolSpec


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec[Any]] = ()) -> None:
        self._specs: dict[str, ToolSpec[Any]] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec[Any]) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec[Any] | None:
        return self._specs.get(name)

    def names(self) -> list[str]:
        return list(self._specs)

    def schemas(self) -> list[ToolSchema]:
        return [spec.schema() for spec in self._specs.values()]

    def subset(self, names: Iterable[str]) -> ToolRegistry:
        wanted = list(names)
        unknown = [name for name in wanted if name not in self._specs]
        if unknown:
            raise ValueError(f"Unknown tool(s): {', '.join(unknown)}")
        return ToolRegistry(self._specs[name] for name in wanted)

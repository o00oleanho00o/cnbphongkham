"""The judging service of this plugin as other plugins use it (``ctx.provide("judge", ...)``): the key, the
model and the day's allowance stay here, behind the ``JudgeService`` contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .plugin import JevPlugin


class SharedJudge:
    def __init__(self, plugin: JevPlugin) -> None:
        self._plugin = plugin

    async def ready(self) -> bool:
        return await self._plugin.ready()

    async def ask(
        self,
        states: Sequence[Any],
        questions: Mapping[str, Mapping[str, Any]],
        *,
        timeout_s: float,
    ) -> list[dict[str, Any]]:
        return await self._plugin.judge(states, questions, timeout_s=timeout_s)

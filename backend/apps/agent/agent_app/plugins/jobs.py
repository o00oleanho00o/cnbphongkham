"""Runs the background jobs of the enabled plugins: starts each one, starts it again (after a growing pause)
when it ends or fails, and cancels it when its plugin goes away."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from agent_app.plugins.host import PluginJob

MAX_ERROR_CHARS: Final = 500

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class JobSettings:
    tick_s: float = 2.0
    restart_s: tuple[float, ...] = (1.0, 5.0, 30.0, 120.0)
    """The pause before a restart, by how many times in a row the job stopped soon after starting."""
    stable_s: float = 60.0
    """A run at least this long counts as healthy: the next restart waits the shortest pause again."""
    stop_grace_s: float = 5.0


@dataclass(slots=True)
class _Run:
    job: PluginJob
    task: asyncio.Task[None]
    started: float


class JobRunner:
    def __init__(
        self,
        jobs: Callable[[], Sequence[PluginJob]],
        *,
        settings: JobSettings | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._jobs = jobs
        self.settings = settings or JobSettings()
        self._clock = clock
        self._runs: dict[str, _Run] = {}
        self._failures: dict[str, int] = {}
        self._errors: dict[str, str] = {}
        self._retry_at: dict[str, float] = {}

    @property
    def running(self) -> list[str]:
        return sorted(self._runs)

    def status(self) -> list[dict[str, Any]]:
        names = {job.key for job in self._jobs()} | set(self._runs)
        return [
            {"name": key, "running": key in self._runs, "error": self._errors.get(key)}
            for key in sorted(names)
        ]

    async def run(self) -> None:
        while True:
            try:
                await self.sync()
            except Exception as err:  # the next tick tries again
                logger.warning("job tick failed (%s)", type(err).__name__)
            await asyncio.sleep(self.settings.tick_s)

    async def sync(self) -> None:
        wanted = {job.key: job for job in self._jobs()}
        for key, run in list(self._runs.items()):
            if wanted.get(key) is not run.job:
                await self._cancel(key)
            elif run.task.done():
                self._ended(key, run)
        for key in [k for k in self._retry_at if k not in wanted]:
            for state in (self._failures, self._errors, self._retry_at):
                state.pop(key, None)
        for key, job in wanted.items():
            if key in self._runs or self._clock() < self._retry_at.get(key, -math.inf):
                continue
            task = asyncio.create_task(job.run(), name=f"plugin job {key}")
            self._runs[key] = _Run(job, task, self._clock())
            logger.info("plugin job %s started", key)

    async def close(self) -> None:
        for key in list(self._runs):
            await self._cancel(key)

    def _ended(self, key: str, run: _Run) -> None:
        del self._runs[key]
        error = None if run.task.cancelled() else run.task.exception()
        short = self._clock() - run.started < self.settings.stable_s
        failures = self._failures.get(key, 0) + 1 if short else 1
        self._failures[key] = failures
        pauses = self.settings.restart_s
        self._retry_at[key] = self._clock() + pauses[min(failures, len(pauses)) - 1]
        if error is None:
            self._errors[key] = "the job ended"
            logger.warning("plugin job %s ended; starting it again", key)
        else:
            text = str(error)
            self._errors[key] = (f"{type(error).__name__}: {text}" if text else type(error).__name__)[
                :MAX_ERROR_CHARS
            ]
            logger.warning("plugin job %s failed (%s); starting it again", key, type(error).__name__)

    async def _cancel(self, key: str) -> None:
        run = self._runs.pop(key)
        run.task.cancel()
        done, _ = await asyncio.wait({run.task}, timeout=self.settings.stop_grace_s)
        if not done:
            logger.warning("plugin job %s did not stop within %.0f s", key, self.settings.stop_grace_s)
        elif not run.task.cancelled():
            run.task.exception()  # retrieved, so asyncio does not report it as lost
        logger.info("plugin job %s stopped", key)

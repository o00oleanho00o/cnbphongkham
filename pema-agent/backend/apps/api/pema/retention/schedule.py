"""The periodic retention run of a process (new module, no TS source).

The worker starts it with scope ``agent`` and the API process with scope ``clinic`` (see
``pema.retention.runner`` for why). Like ``start_daily_task`` of the original: an error in a pass is logged
and the loop goes on, a failing cleanup must not take the process down; the returned task is the handle to
cancel at shutdown.

The first pass waits ``initial_delay_seconds`` instead of running at once: right after a restart the process
is busy with its own start (accounts, queues) and the job has no deadline.
"""

from __future__ import annotations

import asyncio

from pema.retention.runner import RetentionRunner
from pema.shared.logger import create_logger

log = create_logger("retention-schedule")

DEFAULT_INITIAL_DELAY_SECONDS = 60.0


def start_retention_loop(
    runner: RetentionRunner,
    *,
    interval_seconds: float,
    initial_delay_seconds: float = DEFAULT_INITIAL_DELAY_SECONDS,
) -> asyncio.Task[None] | None:
    """Start the loop; ``None`` when ``interval_seconds`` is 0 (periodic run off; the CLI still works)."""
    if interval_seconds <= 0:
        log.info("periodic retention is off", scopes=[s.value for s in runner.scopes])
        return None

    async def one_pass() -> None:
        try:
            reports = await runner.run_active_clinics()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            log.error("retention pass failed", err=err)
            return
        failed = sum(1 for r in reports if r.failed)
        if failed:
            log.warning("retention pass finished with failures", runs=len(reports), failed=failed)

    async def loop() -> None:
        await asyncio.sleep(initial_delay_seconds)
        while True:
            await one_pass()
            await asyncio.sleep(interval_seconds)

    return asyncio.get_running_loop().create_task(loop(), name="retention")

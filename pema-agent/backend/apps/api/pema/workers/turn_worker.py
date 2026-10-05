"""Agent turn worker: claims ``TurnJob`` s from the ``TurnQueue`` and runs them (PLAN-AI01 section 4).

New module (no zalo-agent source; PORT-MAP "Modules with no zalo-agent source"). In the original one Node
process
received the Zalo event, batched it and ran the turn in the same event loop. Here the webhook/poller and
the batcher
live in the API process, which only enqueues; this worker (role ``agent_worker``, no privilege on
``clinic.*``)
consumes the queue and runs ``message_turn_processor.process_turn_job``.

* ``concurrency`` jobs run at the same time; two jobs of one thread never overlap because ``process_turn_job``
  holds the Redis ``ThreadLock`` of ``(account, thread)``;
* ``claim`` blocks for ``block_seconds`` so an idle worker does not spin; ``stop()`` finishes the jobs in
flight
  and returns;
* a job that raises outside the turn is nacked by ``process_turn_job`` itself; anything that still escapes is
  logged here and never kills the loop;
* ``run()`` starts nothing else. Starting the personal accounts (``AccountManager.start_all_accounts``), the
  friend sweep and the process wiring (``pema/workers/main.py``) belong to package G.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pema.channels.message_turn_processor import TurnServices, process_turn_job
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import TurnJob, TurnQueue

log = create_logger("turn-worker")


@dataclass(frozen=True)
class TurnWorkerOptions:
    concurrency: int = 4
    block_seconds: float = 5.0
    error_backoff_seconds: float = 1.0
    """Pause after the queue itself failed (Redis down), so a broken queue does not become a busy loop."""


class TurnWorker:
    def __init__(
        self, services: TurnServices, queue: TurnQueue, options: TurnWorkerOptions | None = None
    ) -> None:
        self._services = services
        self._queue = queue
        self._options = options or TurnWorkerOptions()
        self._stopping = asyncio.Event()
        self._in_flight: set[asyncio.Task[None]] = set()

    def stop(self) -> None:
        """Stop claiming new jobs; ``run`` returns after the jobs in flight finish."""
        self._stopping.set()

    async def run(self) -> None:
        slots = asyncio.Semaphore(self._options.concurrency)
        log.info("turn worker started", concurrency=self._options.concurrency)
        while not self._stopping.is_set():
            await slots.acquire()
            if self._stopping.is_set():
                slots.release()
                break
            try:
                job = await self._queue.claim(self._options.block_seconds)
            except Exception as err:
                slots.release()
                log.error("claiming from the turn queue failed", err=err)
                await asyncio.sleep(self._options.error_backoff_seconds)
                continue
            if job is None:
                slots.release()
                continue
            task = asyncio.get_running_loop().create_task(self._run_one(slots, job))
            self._in_flight.add(task)
            task.add_done_callback(self._in_flight.discard)
        if self._in_flight:
            await asyncio.gather(*list(self._in_flight), return_exceptions=True)
        log.info("turn worker stopped")

    async def _run_one(self, slots: asyncio.Semaphore, job: TurnJob) -> None:
        try:
            await process_turn_job(self._services, self._queue, job)
        except Exception as err:
            log.error("turn job crashed", err=err)
        finally:
            slots.release()

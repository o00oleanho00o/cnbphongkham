"""Entry point of the worker process: ``python -m pema.workers.main`` (package G, no TS source).

The worker connects as role ``agent_worker`` (no privilege on ``clinic.*``) and runs, in one event loop:

* the TURN worker: claims ``TurnJob`` s from the Redis queue and runs them through the engine. The policy
  hooks ``before_llm`` / ``after_llm`` / ``on_outbound`` run IN this process (they are part of the engine and
  of the turn pipeline);
* the SCHEDULER loop (S): due jobs, caps, delivery attempts, recovery;
* the KB INGEST worker (D3): parse, chunk, embed;
* the channel accounts of this process: the bot accounts (listening when the mode is polling, send-only when
  it is webhook), and the personal accounts behind the bridge when the flag is on, plus their friend sweep;
* the MCP manager (D5), the settings refresh loop, the KB availability snapshot;
* housekeeping: ``RedisTurnQueue.reclaim_expired`` (a job whose worker died goes back to the queue), the purge
  of ``agent.channel_update_seen``, and the retention run of scope ``agent`` (``pema.retention``: history,
  memories,
  trace, job runs, image descriptions and the media files; it replaces the former daily media/trace cleanup
  and
  takes its periods from ``PEMA_RETENTION_*``, falling back to ``AGENT_TRACE_RETENTION_DAYS`` and
  ``MEDIA_RETENTION_DAYS``).

The CRM rule runner is NOT here: it reads ``clinic.*`` and so runs in the API process (CONTRACTS decision 7).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pema.channels.message_turn_processor import TurnServices
from pema.channels.zalo_bot.bot_account_runner import ClientFactory
from pema.channels.zalo_personal.friend_auto_accept_sweep import (
    AutoAcceptConfig,
    PendingRequestRef,
    QuetDeps,
    RunningAccountRef,
    start_friend_auto_accept_sweep,
)
from pema.channels.zalo_personal.friend_request_store import FriendRequestStore
from pema.composition.intake import BotStack, PersonalStack, build_bot_stack, build_personal_stack
from pema.composition.runtime import ProcessRole, Runtime, build_runtime
from pema.config.env import Settings, get_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import get_installation_clinic_id
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema.knowledge.kb_extract_timeout_boot_guard import kiem_tra_kb_extract_timeout
from pema.knowledge.kb_ingest_worker import KbIngestWorker
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner
from pema.retention.schedule import start_retention_loop
from pema.shared.logger import configure_logging, create_logger
from pema.workers.kb_ingest_worker import chay_mai_mai, tao_embedder
from pema.workers.scheduler_worker import run_scheduler_worker
from pema.workers.turn_worker import TurnWorker, TurnWorkerOptions
from pema_contracts.policy import DEFAULT_PROFILES, PiiMaskMode, PolicyContext, effective_profile_key

log = create_logger("workers.main")

RECLAIM_INTERVAL_S = 60.0
PURGE_INTERVAL_S = 6 * 60 * 60.0


def summary_mask_of(hooks: object, ctx: PolicyContext) -> Callable[[str], str] | None:
    """``PolicyHooks.mask_text`` bound to ``ctx`` (the optional method the real hooks expose next to the
    eight), or ``None`` when the hooks cannot mask."""
    mask: Any = getattr(hooks, "mask_text", None)
    if not callable(mask):
        return None

    def apply(prompt: str) -> str:
        return str(mask(ctx, prompt))

    return apply


def build_turn_services(rt: Runtime) -> TurnServices:
    """What a turn needs, from the runtime of the worker."""

    async def summarize_thread(clinic_id: UUID, account_id: str, thread_id: str) -> None:
        # The summary prompt is built from the RAW history: under a profile that masks PII the prompt goes
        # through the mask of the policy first, and without that mask no summary is made at all (fail closed).
        account = await rt.accounts.get_account(clinic_id, account_id)
        if account is None:
            return
        agent = await rt.agents.get_agent_for_account(clinic_id, account)
        profile = DEFAULT_PROFILES[effective_profile_key(account.policy_profile, agent.policy_profile)]
        prompt_filter: Callable[[str], str] | None = None
        if profile.pii_mask is PiiMaskMode.REQUIRED:
            ctx = PolicyContext(
                clinic_id=clinic_id,
                account_id=account.id,
                agent_id=agent.id,
                channel=account.channel,
                thread_id=thread_id,
                profile=profile,
            )
            prompt_filter = summary_mask_of(rt.hooks, ctx)
            if prompt_filter is None:
                log.warning(
                    "summary skipped: the profile masks PII but the policy cannot", account_id=account_id
                )
                return
        await rt.conversation.summarizer.maybe_summarize_thread(
            clinic_id, account_id, thread_id, prompt_filter=prompt_filter
        )

    return TurnServices(
        engine=rt.engine,
        history=rt.conversation,
        usage=rt.conversation,
        accounts=rt.accounts,
        agents=rt.agents,
        hooks=rt.hooks,
        pending=rt.pending_inbox,
        registry=rt.channels,
        thread_lock=rt.thread_lock,
        clinic_actions=rt.clinic_actions,
        persist_images=rt.media_images.persist,
        summarize_thread=summarize_thread,
    )


async def _every(interval_s: float, label: str, work: Callable[[], Awaitable[object]]) -> None:
    while True:
        await asyncio.sleep(interval_s)
        try:
            await work()
        except Exception as err:
            log.error("periodic job failed", err=err, label=label)


def _friend_sweep(rt: Runtime, personal: PersonalStack) -> Callable[[], None]:
    friends = FriendRequestStore(rt.db)

    def running() -> list[RunningAccountRef]:
        return [
            RunningAccountRef(info.clinic_id, info.id, account.api)
            for info in personal.manager.get_running_accounts()
            if (account := personal.manager.get_running(info.clinic_id, info.id)) is not None
        ]

    async def config_of(clinic_id: UUID, account_id: str) -> AutoAcceptConfig | None:
        account = await rt.accounts.get_account(clinic_id, account_id)
        if account is None:
            return None
        return AutoAcceptConfig(account.auto_accept_friends, account.auto_accept_friend_delay_minutes)

    async def overdue(clinic_id: UUID, account_id: str, before: datetime) -> list[PendingRequestRef]:
        rows = await friends.lay_friend_request_qua_han(clinic_id, account_id, before)
        return [PendingRequestRef(r.from_uid) for r in rows]

    deps = QuetDeps(
        ds_account=running,
        get_config=config_of,
        lay_qua_han=overdue,
        xoa=friends.xoa_friend_request,
        accept=lambda api, uid: api.accept_friend_request(uid),
    )
    return start_friend_auto_accept_sweep(deps, now=lambda: datetime.now(UTC))


class WorkerHandle:
    """A running worker: ``stop`` ends it, ``wait`` returns when it has shut down."""

    def __init__(self, stop: asyncio.Event, done: asyncio.Task[None]) -> None:
        self._stop = stop
        self._done = done

    def stop(self) -> None:
        self._stop.set()

    async def wait(self) -> None:
        await self._done


async def _run(
    rt: Runtime,
    stop: asyncio.Event,
    started: asyncio.Event | None,
    bot_client_factory: ClientFactory | None = None,
    with_scheduler: bool = True,
) -> None:
    bot: BotStack = build_bot_stack(rt, client_factory=bot_client_factory)
    personal = build_personal_stack(rt, bot_manager=bot.manager)
    services = build_turn_services(rt)
    turn_worker = TurnWorker(services, rt.turn_queue, TurnWorkerOptions())
    kb_worker = KbIngestWorker(rt.db, embedder=tao_embedder(), data_dir=rt.settings.data_dir)
    stop_friend_sweep: Callable[[], None] | None = None
    graceful: list[asyncio.Task[None]] = []
    periodic: list[asyncio.Task[None]] = []
    retention_task: asyncio.Task[None] | None = None
    try:
        await rt.snapshot.refresh(await get_installation_clinic_id(rt.db, verify=True))
        rt.snapshot.start_refresh_loop(rt.clinic_ids)
        rt.kb_availability.start()
        await rt.kb_availability.refresh()
        await rt.mcp.manager.start()

        # The accounts of this process register their channels in ``rt.channels`` (the registry the turn
        # processor, the scheduler and the tools look channels up in).
        await bot.manager.start_all()
        if rt.settings.zalo_personal_enabled:
            await personal.manager.start_all_accounts()
            stop_friend_sweep = _friend_sweep(rt, personal)

        loop = asyncio.get_running_loop()
        # These three end by themselves when ``stop`` is set (a turn in flight is finished, not cut).
        graceful = [
            loop.create_task(turn_worker.run(), name="turn-worker"),
            loop.create_task(chay_mai_mai(kb_worker, rt.db, stop), name="kb-ingest"),
        ]
        if with_scheduler:
            graceful.append(
                loop.create_task(
                    run_scheduler_worker(rt.scheduler_deps, lock_backend=rt.lock_backend, stop=stop),
                    name="scheduler",
                )
            )
        periodic = [
            loop.create_task(_every(RECLAIM_INTERVAL_S, "reclaim", rt.turn_queue.reclaim_expired)),
            loop.create_task(_every(PURGE_INTERVAL_S, "dedupe-purge", lambda: _purge_dedupe(rt, bot))),
        ]
        retention_task = start_retention_loop(
            RetentionRunner(
                rt.db,
                lambda: policy_from_settings(rt.settings, get_tuning_int),
                media=rt.media,
                scopes=(Scope.AGENT,),
            ),
            interval_seconds=rt.settings.retention_interval_seconds,
        )
        log.info("worker started", role=rt.role.value)
        if started is not None:
            started.set()
        await stop.wait()
    finally:
        turn_worker.stop()
        stop.set()
        for task in [*periodic, *([retention_task] if retention_task is not None else [])]:
            task.cancel()
        for result in await asyncio.gather(*graceful, *periodic, return_exceptions=True):
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                log.error("worker task ended with an error", err=result)
        if retention_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await retention_task
        if stop_friend_sweep is not None:
            stop_friend_sweep()
        await rt.mcp.manager.stop()
        await bot.manager.stop_all()
        if rt.settings.zalo_personal_enabled:
            await personal.manager.stop_all_accounts()
        await personal.bridge.aclose()
        await rt.close()
        log.info("worker stopped")


async def _purge_dedupe(rt: Runtime, bot: BotStack) -> None:
    removed = await bot.dedupe.purge(await rt.clinic_id())
    if removed:
        log.info("purged update marks", removed=removed)


async def start_worker(
    rt: Runtime, *, bot_client_factory: ClientFactory | None = None, with_scheduler: bool = True
) -> WorkerHandle:
    """Start the worker on a prepared runtime (the integration tests give theirs and a fake Bot API client).
    Returns when it is up."""
    stop = asyncio.Event()
    started = asyncio.Event()
    done = asyncio.get_running_loop().create_task(
        _run(rt, stop, started, bot_client_factory, with_scheduler), name="worker"
    )
    waiter = asyncio.get_running_loop().create_task(started.wait())
    await asyncio.wait({waiter, done}, return_when=asyncio.FIRST_COMPLETED)
    if done.done():
        waiter.cancel()
        await done
    return WorkerHandle(stop, done)


async def main(settings: Settings | None = None) -> None:
    config = settings or get_settings()
    configure_logging(
        config.log_level,
        file_enabled=config.log_file_enabled,
        log_dir=config.log_dir,
        keep_days=config.log_file_keep_days,
    )
    kiem_tra_kb_extract_timeout()
    rt = build_runtime(config, ProcessRole.WORKER)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows loops cannot add signal handlers
            loop.add_signal_handler(sig, stop.set)
    await _run(rt, stop, None)


def main_cli() -> None:
    ensure_selector_event_loop_policy()
    asyncio.run(main())


if __name__ == "__main__":
    main_cli()

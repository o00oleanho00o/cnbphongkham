"""The outbox consumer: the delivery chain of one notice (package O, step O3). New module, no zalo-agent
original.

``run_once`` claims the due rows of ``clinic.notification_outbox`` (a lease, so two consumers never take one
row) and walks each along its chain. Per recipient kind:

``user``
    1. in-app, now: the notice is in ``GET /me/notifications``; the live event makes open screens reload;
    2. push, now, when the clinic switched push on, the provider is enabled and the operator has a token;
    3. the personal Zalo bell, ``ack_timeout`` (default 180 s) later, only when the operator linked a Zalo id,
       the notice was not acknowledged meanwhile, and the operator is not in quiet hours (an ``urgent`` notice
       rings anyway). An ack (``POST /notifications/{id}/ack`` or opening the deep link) ends the chain.
``team_group``
    posted once to the configured group; no ack. Unset or switched off: skipped and logged.
``on_call``
    the 24/7 contact of package M, through the internal account, at once; no in-app, no push, and the clinic's
    switches do not apply (the on-call number is the last link of every routing chain). The number is chosen
    from the rows when it is sent and is not stored.

Every attempt writes one ``notification_log`` row (provider, attempt, status, latency in ms, a short error
code). A step that fails for a reason that may pass (a transport error, the account not running) is retried
with a growing delay, at most ``MAX_ATTEMPTS`` times; a refusal by a guard is final. The consumer raises
nothing for a provider: it turns it into a result. A crash inside one row is contained, the row is retried
later, and a row that keeps crashing ends as ``failed``.

Latency: ``perf`` (``time.perf_counter`` by default) times every provider call; the numbers go to the log.
Logs carry ids, codes and counts only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pema.clinic.actions.notification_chain import MAX_ATTEMPTS, backoff_s, in_quiet_hours
from pema.clinic.actions.notifications import OutboxNotification
from pema.notify.providers import (
    InAppProvider,
    OnCallBellProvider,
    PushProvider,
    TeamGroupProvider,
    ZaloBellProvider,
    send_push,
)
from pema.notify.types import (
    ERR_DISABLED,
    ERR_EXCEPTION,
    ERR_NO_ZALO_LINK,
    ERR_QUIET_HOURS,
    ChainStore,
    StepResult,
)
from pema.shared.logger import create_logger
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationRecipientKind,
    NotificationState,
    NotifySettingsOut,
)

log = create_logger("notify.consumer")

BELL_STEP = "bell"
DONE_STEP = "done"
DEFAULT_BATCH = 20


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ConsumerReport:
    claimed: int
    crashed: int = 0


class NotificationConsumer:
    def __init__(
        self,
        *,
        store: ChainStore,
        in_app: InAppProvider,
        bell: ZaloBellProvider,
        group: TeamGroupProvider,
        on_call: OnCallBellProvider,
        push: PushProvider | None = None,
        clock: Callable[[], datetime] = _utc_now,
        perf: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._store = store
        self._in_app = in_app
        self._bell = bell
        self._group = group
        self._on_call = on_call
        self._push = push
        self._clock = clock
        self._perf = perf

    # ----------------------------------------------------------------------------------- the loop
    async def run_once(self, limit: int = DEFAULT_BATCH) -> ConsumerReport:
        now = self._clock()
        notices = await self._store.claim_due(now, limit)
        crashed = 0
        for notice in notices:
            try:
                await self._process(notice, now)
            except Exception as err:
                crashed += 1
                log.error("notice processing crashed", err=err, notice_id=str(notice.id))
                await self._crash(notice, now)
        return ConsumerReport(claimed=len(notices), crashed=crashed)

    async def _crash(self, notice: OutboxNotification, now: datetime) -> None:
        attempts = notice.attempts + 1
        final = attempts >= MAX_ATTEMPTS
        await self._store.settle(
            notice.id,
            state=NotificationState.FAILED if final else NotificationState.PENDING,
            chain_step=DONE_STEP if final else notice.chain_step,
            next_attempt_at=now + timedelta(seconds=backoff_s(attempts)),
            attempts=attempts,
        )

    async def _process(self, notice: OutboxNotification, now: datetime) -> None:
        if notice.acked:
            await self._store.settle(
                notice.id,
                state=NotificationState.SENT,
                chain_step=DONE_STEP,
                next_attempt_at=now,
                attempts=notice.attempts,
            )
            return
        settings = await self._store.load_settings()
        kind = notice.recipient_kind
        if kind is NotificationRecipientKind.TEAM_GROUP:
            await self._team_group(notice, settings, now)
        elif kind is NotificationRecipientKind.ON_CALL:
            await self._on_call_step(notice, settings, now)
        elif notice.chain_step == BELL_STEP:
            await self._bell_step(notice, settings, now)
        else:
            await self._first_step(notice, settings, now)

    # ---------------------------------------------------------------------------------- bookkeeping
    async def _timed(self, step: Any) -> tuple[StepResult, int]:
        started = self._perf()
        try:
            result: StepResult = await step
        except Exception as err:
            log.error("provider raised", err=err)
            result = StepResult.failed(ERR_EXCEPTION, retryable=True)
        return result, round((self._perf() - started) * 1000)

    async def _log(
        self,
        notice: OutboxNotification,
        provider: NotificationProvider,
        attempt: int,
        result: StepResult,
        latency_ms: int | None = None,
    ) -> None:
        await self._store.record_attempt(
            notice.id,
            provider,
            attempt=attempt,
            status=result.status,
            latency_ms=latency_ms,
            error_code=result.error_code,
        )
        log.info(
            "notice step",
            notice_id=str(notice.id),
            provider=provider.value,
            status=result.status.value,
            code=result.error_code,
            latency_ms=latency_ms,
        )

    async def _finish_single(
        self,
        notice: OutboxNotification,
        now: datetime,
        provider: NotificationProvider,
        result: StepResult,
        latency_ms: int,
        *,
        skipped_state: NotificationState,
        chain_step: str | None,
    ) -> None:
        """Log one attempt of a single-step row and settle it: sent, skipped, retried or failed."""
        attempt = notice.attempts + 1
        await self._log(notice, provider, attempt, result, latency_ms)
        if result.status is NotificationLogStatus.SENT:
            state, retry = NotificationState.SENT, False
        elif result.status is NotificationLogStatus.SKIPPED:
            state, retry = skipped_state, False
        else:
            retry = result.retryable and attempt < MAX_ATTEMPTS
            state = NotificationState.PENDING if retry else NotificationState.FAILED
        await self._store.settle(
            notice.id,
            state=state,
            chain_step=chain_step if retry else DONE_STEP,
            next_attempt_at=now + timedelta(seconds=backoff_s(attempt)) if retry else now,
            attempts=attempt,
        )

    # --------------------------------------------------------------------------------------- steps
    async def _team_group(
        self, notice: OutboxNotification, settings: NotifySettingsOut, now: datetime
    ) -> None:
        result, ms = await self._timed(self._group.send(notice.payload, settings))
        await self._finish_single(
            notice,
            now,
            NotificationProvider.TEAM_GROUP,
            result,
            ms,
            skipped_state=NotificationState.SKIPPED,
            chain_step=None,
        )

    async def _on_call_step(
        self, notice: OutboxNotification, settings: NotifySettingsOut, now: datetime
    ) -> None:
        rows = await self._store.list_on_call()
        result, ms = await self._timed(self._on_call.send(notice.payload, rows, settings, now))
        await self._finish_single(
            notice,
            now,
            NotificationProvider.ZALO_BELL,
            result,
            ms,
            skipped_state=NotificationState.SKIPPED,
            chain_step=None,
        )

    async def _first_step(
        self, notice: OutboxNotification, settings: NotifySettingsOut, now: datetime
    ) -> None:
        """In-app now, push now, then either the wait for the bell or the end of the chain."""
        user_id = _user_of(notice)
        attempt = notice.attempts + 1
        target = await self._store.load_target(user_id)
        delivered = False
        failed = False

        if settings.in_app_enabled:
            result, ms = await self._timed(self._in_app.send(notice.id))
            await self._log(notice, NotificationProvider.IN_APP, attempt, result, ms)
            delivered = delivered or result.status is NotificationLogStatus.SENT
            failed = failed or result.status is NotificationLogStatus.FAILED
        else:
            await self._log(notice, NotificationProvider.IN_APP, attempt, StepResult.skipped(ERR_DISABLED))

        if settings.push_enabled:
            started = self._perf()
            result, push_result = await send_push(self._push, target, notice.payload)
            ms = round((self._perf() - started) * 1000)
            await self._log(notice, NotificationProvider.PUSH, attempt, result, ms)
            delivered = delivered or result.status is NotificationLogStatus.SENT
            failed = failed or result.status is NotificationLogStatus.FAILED
            if push_result is not None:
                for token_id in push_result.dead_token_ids:
                    await self._store.drop_push_token(token_id)

        if settings.bell_enabled and target.zalo_user_id:
            await self._store.settle(
                notice.id,
                state=NotificationState.PENDING,
                chain_step=BELL_STEP,
                next_attempt_at=now + timedelta(seconds=settings.ack_timeout_s),
                attempts=0,
            )
            return
        bell_skip = ERR_NO_ZALO_LINK if settings.bell_enabled else ERR_DISABLED
        await self._log(notice, NotificationProvider.ZALO_BELL, attempt, StepResult.skipped(bell_skip))
        if delivered:
            state = NotificationState.SENT
        elif failed:
            state = NotificationState.FAILED
        else:
            state = NotificationState.SKIPPED
        await self._store.settle(
            notice.id, state=state, chain_step=DONE_STEP, next_attempt_at=now, attempts=attempt
        )

    async def _bell_step(
        self, notice: OutboxNotification, settings: NotifySettingsOut, now: datetime
    ) -> None:
        """``ack_timeout`` passed. Ring the personal Zalo unless the notice was acknowledged meanwhile."""
        user_id = _user_of(notice)
        if await self._store.is_acked(notice.id):
            await self._store.settle(
                notice.id,
                state=NotificationState.SENT,
                chain_step=DONE_STEP,
                next_attempt_at=now,
                attempts=notice.attempts,
            )
            return
        target = await self._store.load_target(user_id)
        urgent = _is_urgent(notice.payload)
        if not urgent and in_quiet_hours(target.quiet_start, target.quiet_end, now):
            await self._finish_single(
                notice,
                now,
                NotificationProvider.ZALO_BELL,
                StepResult.skipped(ERR_QUIET_HOURS),
                0,
                skipped_state=NotificationState.SENT,
                chain_step=BELL_STEP,
            )
            return
        result, ms = await self._timed(self._bell.send(notice.payload, target, settings))
        await self._finish_single(
            notice,
            now,
            NotificationProvider.ZALO_BELL,
            result,
            ms,
            skipped_state=NotificationState.SENT,
            chain_step=BELL_STEP,
        )


def _user_of(notice: OutboxNotification) -> UUID:
    """The recipient of a ``user`` row (the table's CHECK guarantees there is one)."""
    if notice.recipient_user_id is None:
        raise ValueError("a user notice without a recipient")
    return notice.recipient_user_id


def _is_urgent(payload: Mapping[str, Any]) -> bool:
    return payload.get("urgency") == "urgent"

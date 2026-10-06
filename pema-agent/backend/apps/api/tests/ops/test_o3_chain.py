"""The delivery chain of the notification outbox (package O, step O3).

New tests (no zalo-agent original). No database, no network, no sleep: ``InMemoryChainStore``, a ``FakeClock``,
a fake internal sender and fake push providers. A step of the chain is a call of ``run_once`` after the clock
moved. Covered: in-app immediately; the bell after ``ack_timeout`` only when not acknowledged; an ack stops the
chain; the team group is posted once; quiet hours (an urgent notice still rings); push through the fake
provider and a real provider that stays disabled; bounded retries; the on-call step; a crash inside one row;
the PII guard on the text; the measured latency of every step (fake providers).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from pema.care.routing_types import OnCallRow
from pema.clinic.actions.notification_chain import PushTarget, in_quiet_hours
from pema.clinic.actions.notifications import UnsafeNotificationPayloadError, serialize_payload
from pema.notify.consumer import NotificationConsumer
from pema.notify.providers import (
    FakePushProvider,
    FcmApnsPushProvider,
    InAppProvider,
    OnCallBellProvider,
    PushCredentials,
    PushCredentialsMissingError,
    PushNotImplementedError,
    TeamGroupProvider,
    ZaloBellProvider,
)
from pema.notify.testing import (
    EPOCH,
    FakeClock,
    FakeInternalSender,
    InMemoryChainStore,
    StepClock,
    payload,
    settings,
    target,
)
from pema.notify.text import UnsafeTextError, render_chat_text
from pema.notify.types import InternalTargetKind, StepResult
from pema_contracts.live import LiveEventType
from pema_contracts.ops import (
    NotificationLogStatus as Status,
)
from pema_contracts.ops import (
    NotificationPayload,
    NotificationRecipientKind,
    NotificationState,
)
from pema_contracts.ops import (
    NotificationProvider as Provider,
)

OPERATOR = UUID(int=11)
USER = NotificationRecipientKind.USER
GROUP = NotificationRecipientKind.TEAM_GROUP
ON_CALL = NotificationRecipientKind.ON_CALL


class Rig:
    def __init__(self, *, push: Any = None) -> None:
        self.clock = FakeClock()
        self.store = InMemoryChainStore(self.clock)
        self.sender = FakeInternalSender()
        self.events: list[tuple[LiveEventType, UUID | None]] = []
        self.consumer = NotificationConsumer(
            store=self.store,
            in_app=InAppProvider(emit=lambda kind, ident: self.events.append((kind, ident))),
            bell=ZaloBellProvider(self.sender),
            group=TeamGroupProvider(self.sender),
            on_call=OnCallBellProvider(self.sender),
            push=push,
            clock=self.clock,
            perf=StepClock(0.005),
        )

    def row(self, notice_id: UUID) -> Any:
        return self.store.rows[notice_id]

    async def run(self) -> int:
        return (await self.consumer.run_once()).claimed


# ------------------------------------------------------------------------------------------ in-app
async def test_in_app_is_immediate_and_the_bell_waits_for_the_ack_timeout() -> None:
    rig = Rig()
    notice = rig.store.add(USER, OPERATOR)
    assert await rig.run() == 1
    assert rig.events == [(LiveEventType.NOTIFICATIONS_CHANGED, notice)]
    assert (Provider.IN_APP, Status.SENT) in rig.store.providers_logged(notice)
    assert rig.sender.sent == []
    row = rig.row(notice)
    assert row.state is NotificationState.PENDING
    assert row.chain_step == "bell"
    assert (row.next_attempt_at - EPOCH).total_seconds() == 180


async def test_the_bell_rings_after_the_timeout_when_nobody_acknowledged() -> None:
    rig = Rig()
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    rig.clock.advance(seconds=179)
    assert await rig.run() == 0
    assert rig.sender.sent == []
    rig.clock.advance(seconds=2)
    assert await rig.run() == 1
    ((where, text),) = rig.sender.sent
    assert where.kind is InternalTargetKind.STAFF
    assert where.ref == "zalo-op-fixture"
    assert "#A1B2" in text
    assert text.startswith("[Pema] ")
    assert rig.row(notice).state is NotificationState.SENT
    assert (Provider.ZALO_BELL, Status.SENT) in rig.store.providers_logged(notice)


async def test_an_ack_before_the_timeout_stops_the_chain() -> None:
    rig = Rig()
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    rig.store.ack(notice)
    rig.clock.advance(seconds=600)
    assert await rig.run() == 0
    assert rig.sender.sent == []
    assert (Provider.ZALO_BELL, Status.SENT) not in rig.store.providers_logged(notice)


async def test_an_ack_that_lands_while_the_row_is_claimed_still_stops_the_bell() -> None:
    rig = Rig()
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    rig.clock.advance(seconds=181)
    rig.row(notice).acked = True  # acked after the row was due, state not yet changed
    await rig.run()
    assert rig.sender.sent == []
    assert rig.row(notice).state is NotificationState.SENT


async def test_without_a_linked_zalo_the_bell_is_skipped_and_logged() -> None:
    rig = Rig()
    rig.store.targets[OPERATOR] = target(OPERATOR, zalo=None)
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    assert (Provider.ZALO_BELL, Status.SKIPPED) in rig.store.providers_logged(notice)
    assert rig.row(notice).state is NotificationState.SENT  # the in-app step was delivered
    rig.clock.advance(seconds=600)
    assert await rig.run() == 0


async def test_switches_off_means_skipped_not_silent() -> None:
    rig = Rig()
    rig.store.settings = settings(in_app_enabled=False, bell_enabled=False)
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    logged = rig.store.providers_logged(notice)
    assert (Provider.IN_APP, Status.SKIPPED) in logged
    assert (Provider.ZALO_BELL, Status.SKIPPED) in logged
    assert rig.row(notice).state is NotificationState.SKIPPED
    assert rig.events == []


# ----------------------------------------------------------------------------------------- quiet hours
def test_quiet_hours_cross_midnight_and_exclude_the_end() -> None:
    from datetime import time

    assert in_quiet_hours(time(22, 0), time(6, 0), EPOCH.replace(hour=16))  # 23:00 on the clinic clock
    assert not in_quiet_hours(time(22, 0), time(6, 0), EPOCH)  # 09:00
    assert not in_quiet_hours(time(8, 0), time(9, 0), EPOCH)  # the end is excluded
    assert not in_quiet_hours(None, None, EPOCH)


async def test_quiet_hours_silence_the_bell_but_an_urgent_notice_still_rings() -> None:
    from datetime import time

    rig = Rig()
    rig.store.targets[OPERATOR] = target(OPERATOR, quiet_start=time(8, 0), quiet_end=time(10, 0))
    calm = rig.store.add(USER, OPERATOR)
    urgent = rig.store.add(USER, OPERATOR, body=payload(urgency="urgent"))
    await rig.run()
    rig.clock.advance(seconds=181)
    await rig.run()
    assert (Provider.ZALO_BELL, Status.SKIPPED) in rig.store.providers_logged(calm)
    assert (Provider.ZALO_BELL, Status.SENT) in rig.store.providers_logged(urgent)
    ((_, text),) = rig.sender.sent
    assert "[KHẨN]" in text


# ----------------------------------------------------------------------------------------- team group
@pytest.mark.parametrize("event", ["claim", "takeover", "shift_end"])
async def test_the_group_is_posted_once_for_claim_takeover_and_shift_end(event: str) -> None:
    rig = Rig()
    notice = rig.store.add(GROUP, body=payload(event=event))
    await rig.run()
    await rig.run()
    rig.clock.advance(seconds=3600)
    await rig.run()
    ((where, _),) = rig.sender.sent
    assert where.kind is InternalTargetKind.GROUP
    assert where.ref == "group-fixture"
    assert rig.row(notice).state is NotificationState.SENT
    assert rig.store.providers_logged(notice) == [(Provider.TEAM_GROUP, Status.SENT)]


async def test_an_unset_group_skips_the_step_and_logs_why() -> None:
    rig = Rig()
    rig.store.settings = settings(team_group_id=None)
    notice = rig.store.add(GROUP)
    await rig.run()
    assert rig.sender.sent == []
    assert rig.row(notice).state is NotificationState.SKIPPED
    entry = rig.store.log[-1]
    assert (entry.provider, entry.status, entry.error_code) == (
        Provider.TEAM_GROUP,
        Status.SKIPPED,
        "group_unset",
    )


# ----------------------------------------------------------------------------------------------- push
async def test_push_goes_through_the_fake_provider_and_a_dead_token_is_forgotten() -> None:
    live, dead = UUID(int=1), UUID(int=2)
    push = FakePushProvider(dead=frozenset({dead}))
    rig = Rig(push=push)
    rig.store.settings = settings(push_enabled=True)
    rig.store.targets[OPERATOR] = target(
        OPERATOR,
        pushes=(PushTarget(live, "android", "tok-a"), PushTarget(dead, "ios", "tok-b")),  # type: ignore[arg-type]
    )
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    ((devices, message),) = push.sent
    assert devices == (live,)
    assert message.deep_link.startswith("/inbox?conversation=")
    assert (Provider.PUSH, Status.SENT) in rig.store.providers_logged(notice)
    assert rig.store.dropped_tokens == [dead]


async def test_push_without_a_token_is_skipped_and_the_bell_still_follows() -> None:
    rig = Rig(push=FakePushProvider())
    rig.store.settings = settings(push_enabled=True)
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    assert (Provider.PUSH, Status.SKIPPED) in rig.store.providers_logged(notice)
    assert rig.row(notice).chain_step == "bell"


def test_the_real_push_provider_stays_disabled_without_credentials() -> None:
    provider = FcmApnsPushProvider()
    assert provider.enabled is False
    with pytest.raises(PushCredentialsMissingError):
        provider.start()
    with pytest.raises(PushCredentialsMissingError):
        FcmApnsPushProvider(PushCredentials(fcm_project_id="", fcm_service_account_json="")).start()
    with pytest.raises(PushNotImplementedError):  # even with credentials the skeleton has no transport
        FcmApnsPushProvider(PushCredentials("project-fixture", "{}")).start()


async def test_the_disabled_real_provider_is_skipped_by_the_chain() -> None:
    rig = Rig(push=FcmApnsPushProvider())
    rig.store.settings = settings(push_enabled=True)
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    codes = [e.error_code for e in rig.store.log if e.provider is Provider.PUSH and e.outbox_id == notice]
    assert codes == ["provider_disabled"]


# --------------------------------------------------------------------------------------------- on call
def _on_call_row(number: str = "0000000001") -> OnCallRow:
    return OnCallRow(
        id=UUID(int=7), zalo_number=number, owner="Trực (mẫu)", valid_from=EPOCH.replace(year=2026, month=1)
    )


async def test_the_on_call_contact_is_rung_at_once_and_the_switches_do_not_apply() -> None:
    rig = Rig()
    rig.store.settings = settings(bell_enabled=False, in_app_enabled=False)
    rig.store.on_call = [_on_call_row()]
    notice = rig.store.add(ON_CALL, body=payload(event="handoff_on_call", summary="Trực 24/7: yêu cầu #A1B2"))
    await rig.run()
    ((where, _),) = rig.sender.sent
    assert where.kind is InternalTargetKind.ON_CALL
    assert where.ref == "0000000001"
    assert rig.store.providers_logged(notice) == [(Provider.ZALO_BELL, Status.SENT)]
    assert rig.events == []  # no in-app step for a number outside the app


async def test_no_on_call_row_is_a_retried_failure_not_a_silent_drop() -> None:
    rig = Rig()
    notice = rig.store.add(ON_CALL)
    await rig.run()
    row = rig.row(notice)
    assert (row.state, row.attempts) == (NotificationState.PENDING, 1)
    assert rig.store.log[-1].error_code == "no_on_call"


# ------------------------------------------------------------------------------------ retries, crash
async def test_a_failing_transport_is_retried_with_a_growing_delay_then_fails() -> None:
    rig = Rig()
    rig.sender.result = StepResult.failed("exception", retryable=True)
    notice = rig.store.add(GROUP)
    delays: list[float] = []
    for _ in range(3):
        await rig.run()
        row = rig.row(notice)
        delays.append((row.next_attempt_at - rig.clock.now).total_seconds())
        rig.clock.advance(seconds=3600)
    assert rig.row(notice).state is NotificationState.FAILED
    assert rig.row(notice).attempts == 3
    assert delays[:2] == [20, 40]
    assert len(rig.sender.sent) == 3


async def test_a_refusal_by_a_guard_is_final() -> None:
    rig = Rig()
    rig.sender.result = StepResult.failed("customer_recipient")
    notice = rig.store.add(GROUP)
    await rig.run()
    assert rig.row(notice).state is NotificationState.FAILED
    assert len(rig.sender.sent) == 1


async def test_a_crash_inside_one_row_is_contained_and_retried_later() -> None:
    rig = Rig()
    boom = rig.store.add(USER, OPERATOR)
    fine = rig.store.add(GROUP)
    original = rig.store.load_target

    async def broken(user_id: UUID) -> Any:
        raise RuntimeError("database went away")

    rig.store.load_target = broken  # type: ignore[method-assign]
    report = await rig.consumer.run_once()
    assert (report.claimed, report.crashed) == (2, 1)
    assert rig.row(fine).state is NotificationState.SENT
    assert rig.row(boom).state is NotificationState.PENDING
    assert rig.row(boom).attempts == 1
    rig.store.load_target = original  # type: ignore[method-assign]


# ------------------------------------------------------------------------------------------ PII guard
def test_the_payload_check_refuses_a_phone_number_and_a_known_full_name() -> None:
    base = NotificationPayload.model_validate(payload(event="takeover"))
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(base.model_copy(update={"summary": "Gọi khách số 0901234567"}))
    with pytest.raises(UnsafeNotificationPayloadError):
        serialize_payload(
            base.model_copy(update={"summary": "Khách Nguyễn Thị Hoa hỏi giá"}),
            forbidden_names=["Nguyễn Thị Hoa"],
        )
    assert serialize_payload(base)["short_code"] == "#A1B2"


def test_a_row_that_skipped_the_serializer_still_cannot_put_a_phone_in_a_chat() -> None:
    with pytest.raises(UnsafeTextError):
        render_chat_text(payload(summary="Gọi 0901234567 gấp"), None)


async def test_an_unsafe_text_is_a_final_failure_and_nothing_is_sent() -> None:
    rig = Rig()
    notice = rig.store.add(GROUP, body=payload(summary="Gọi 0901234567 gấp"))
    await rig.run()
    assert rig.sender.sent == []
    assert rig.row(notice).state is NotificationState.FAILED
    assert rig.store.log[-1].error_code == "unsafe_text"


# ----------------------------------------------------------------------------------------- latency
async def test_every_step_of_the_chain_records_its_latency() -> None:
    """With ``StepClock(0.005)`` each provider call measures 5 ms; the numbers are what the log would hold.
    The report quotes the real figures of a run with fake providers (see the step report)."""
    rig = Rig(push=FakePushProvider())
    rig.store.settings = settings(push_enabled=True)
    rig.store.targets[OPERATOR] = target(OPERATOR, pushes=(PushTarget(UUID(int=1), "android", "tok"),))  # type: ignore[arg-type]
    notice = rig.store.add(USER, OPERATOR)
    await rig.run()
    rig.clock.advance(seconds=181)
    await rig.run()
    latencies = {
        e.provider: e.latency_ms for e in rig.store.log if e.outbox_id == notice and e.status is Status.SENT
    }
    assert set(latencies) == {Provider.IN_APP, Provider.PUSH, Provider.ZALO_BELL}
    assert all(value is not None and value >= 0 for value in latencies.values())
    assert latencies[Provider.IN_APP] == 5
    assert latencies[Provider.ZALO_BELL] == 5

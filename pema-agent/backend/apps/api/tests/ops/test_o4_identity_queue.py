"""One queue, one gap and one cap per clinic identity (package O, step O4). New tests, no zalo-agent original.

No database and no Redis: the identity lookup, the clock, the sleep and the cap counter are fakes, so nothing
sleeps for real. They cover: two operators and the agent on one identity share one gap; separate identities do
not block each other; the daily cap counts proactive sends only; the kill switch blocks every send; an internal
identity is never a way to a customer; the adapter's ``external_message_id`` comes back; the text is sent
exactly as stored (no signature); and the identity of the request, not "an account of the same kind", is the
one used.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from itertools import pairwise
from uuid import UUID, uuid4

import pytest

from pema.agent.testing import make_caps
from pema.channels.identity_send_queue import (
    IdentitySendQueue,
    InMemorySendSlotBackend,
    install_identity_send_queue,
    installed_identity_send_queue,
)
from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.send_reply_in_parts import EnqueueSend, reply_target_from_channel, send_reply_in_parts
from pema.clinic.actions.outbound import OutboundRequest
from pema.composition.outbound import RegistryOutboundDelivery
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind, SendResult, SendStatus, ThreadKind
from pema_contracts.conversations import SenderType
from pema_contracts.errors import ErrorCode
from pema_contracts.ops import EffectiveLimits, IdentityOut, IdentityPurpose, LimitOverrides
from pema_contracts.roles import ActorType
from pema_contracts.testing import FAKE_CLINIC_ID, FakeChannel, InMemoryAccountStore, fake_account_config

THREAD = "synthetic-thread-1"
OPERATOR_A = uuid4()
OPERATOR_B = uuid4()


class FakeTime:
    """A clock that only moves when somebody sleeps, so a test measures the waits it asked for."""

    def __init__(self) -> None:
        self.now = 1_000_000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def identity(
    account_id: str,
    *,
    purpose: IdentityPurpose = IdentityPurpose.CUSTOMER,
    enabled: bool = True,
    kill_switch: bool = False,
    gap: tuple[int, int] = (10, 10),
    cap: int | None = None,
) -> IdentityOut:
    return IdentityOut(
        id=account_id,
        label=f"Danh tính {account_id}",
        channel=ChannelKind.ZALO_PERSONAL,
        purpose=purpose,
        enabled=enabled,
        channel_enabled=True,
        kill_switch_on=kill_switch,
        bridge_state=None,
        overrides=LimitOverrides(),
        effective=EffectiveLimits(send_gap_min_s=gap[0], send_gap_max_s=gap[1], daily_cap=cap),
    )


class Identities:
    """A mutable table the queue reads on every send, like the database does."""

    def __init__(self, *rows: IdentityOut) -> None:
        self.rows = {row.id: row for row in rows}

    async def lookup(self, account_id: str) -> IdentityOut | None:
        return self.rows.get(account_id)


def build_queue(table: Identities, clock: FakeTime) -> IdentitySendQueue:
    return IdentitySendQueue(
        clinic_id=FAKE_CLINIC_ID,
        lookup=table.lookup,
        backend=InMemorySendSlotBackend(clock.clock),
        clock=clock.clock,
        sleep=clock.sleep,
        uniform=lambda low, high: high,
    )


def sender(channel: FakeChannel) -> Callable[[], Awaitable[SendResult]]:
    async def send() -> SendResult:
        return await channel.send_text(THREAD, "Chào chị, em là Long.")

    return send


def make_channel(account_id: str) -> FakeChannel:
    return FakeChannel(caps=make_caps(), account=account_id)


# ------------------------------------------------------------------------------------------------ gap
async def test_agent_and_two_operators_on_one_identity_share_one_gap() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(10, 10))), clock)
    channel = make_channel("long")

    results = [await queue.send("long", sender(channel)) for _who in ("agent", "operator a", "operator b")]

    assert [r.status for r in results] == [SendStatus.SENT] * 3
    assert len(channel.sent) == 3
    # the first send leaves at once; each of the next two waits the whole gap since the one before it
    assert clock.slept == [pytest.approx(10.0), pytest.approx(10.0)]


async def test_concurrent_senders_of_one_identity_leave_one_gap_apart() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(5, 5))), clock)
    channel = make_channel("long")
    left_at: list[float] = []

    async def send() -> SendResult:
        left_at.append(clock.clock())
        return await channel.send_text(THREAD, "Tin mẫu")

    await asyncio.gather(*(queue.send("long", send) for _ in range(3)))

    assert len(left_at) == 3
    assert [b - a for a, b in pairwise(left_at)] == [
        pytest.approx(5.0, abs=0.2),
        pytest.approx(5.0, abs=0.2),
    ]


async def test_separate_identities_do_not_block_each_other() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(30, 30)), identity("hoa", gap=(30, 30))), clock)
    long_channel, hoa_channel = make_channel("long"), make_channel("hoa")

    await queue.send("long", sender(long_channel))
    await queue.send("hoa", sender(hoa_channel))  # a different identity: no wait

    assert clock.slept == []
    assert len(long_channel.sent) == 1
    assert len(hoa_channel.sent) == 1


async def test_a_failed_send_does_not_start_the_gap() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(10, 10))), clock)
    channel = make_channel("long")
    channel.reject_with = SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE)
    await queue.send("long", sender(channel))
    channel.reject_with = None

    await queue.send("long", sender(channel))

    assert clock.slept == []


async def test_the_gap_follows_the_limits_of_the_identity_read_at_send_time() -> None:
    clock = FakeTime()
    table = Identities(identity("long", gap=(10, 10)))
    queue = build_queue(table, clock)
    channel = make_channel("long")
    await queue.send("long", sender(channel))

    table.rows["long"] = identity("long", gap=(0, 0))  # the manager removed the gap
    await queue.send("long", sender(channel))

    assert clock.slept == []


# ------------------------------------------------------------------------------------- cap and kill
async def test_the_daily_cap_counts_proactive_messages_only() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(0, 0), cap=2)), clock)

    replies = [await queue.admit("long", proactive=False) for _ in range(5)]
    first = await queue.admit("long", proactive=True)
    second = await queue.admit("long", proactive=True)
    third = await queue.admit("long", proactive=True)
    after_reply = await queue.admit("long", proactive=False)

    assert all(a.admitted for a in replies)  # replies respect the gap, not the cap
    assert first.admitted
    assert second.admitted
    assert third.rejection is not None
    assert third.rejection.error_code is ErrorCode.CHANNEL_DAILY_CAP_REACHED
    assert after_reply.admitted


async def test_a_message_that_did_not_leave_gives_its_cap_slot_back() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", gap=(0, 0), cap=1)), clock)

    admission = await queue.admit("long", proactive=True)
    await queue.settle(admission, sent=False)
    again = await queue.admit("long", proactive=True)

    assert again.admitted


async def test_the_cap_is_per_identity_not_per_channel() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", cap=1), identity("hoa", cap=1)), clock)

    assert (await queue.admit("long", proactive=True)).admitted
    assert (await queue.admit("hoa", proactive=True)).admitted
    blocked = await queue.admit("long", proactive=True)

    assert blocked.rejection is not None


async def test_the_kill_switch_blocks_admission_and_every_part() -> None:
    clock = FakeTime()
    table = Identities(identity("long", kill_switch=True))
    queue = build_queue(table, clock)
    channel = make_channel("long")

    admission = await queue.admit("long", proactive=False)
    part = await queue.send("long", sender(channel))

    assert admission.rejection is not None
    assert admission.rejection.error_code is ErrorCode.CHANNEL_KILL_SWITCH_ON
    assert part.status is SendStatus.REJECTED
    assert part.error_code is ErrorCode.CHANNEL_KILL_SWITCH_ON
    assert channel.sent == []

    table.rows["long"] = identity("long", kill_switch=False)  # read again on the next message, no cache
    assert (await queue.send("long", sender(channel))).status is SendStatus.SENT


async def test_an_internal_identity_is_refused_for_a_customer_message() -> None:
    queue = build_queue(Identities(identity("notifier", purpose=IdentityPurpose.INTERNAL)), FakeTime())

    admission = await queue.admit("notifier", proactive=False)

    assert admission.rejection is not None
    assert admission.rejection.error_code is ErrorCode.POLICY_DENIED
    assert not await queue.is_customer_facing("notifier")


# ------------------------------------------------------------------------- the delivery over a channel
async def immediate(thread_key: str, task: Callable[[], Awaitable[object]]) -> object:
    return await task()


@pytest.fixture(autouse=True)
def _no_real_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-thread human-like delay of the rate limiter is real time: use an immediate queue here."""
    monkeypatch.setattr("pema.channels.send_reply_in_parts.default_enqueue_send", lambda: immediate)
    install_identity_send_queue(None)


def request(
    account_id: str | None, *, text: str = "Đã duyệt: hẹn gặp chị lúc 9 giờ.", proactive: bool = False
) -> OutboundRequest:
    return OutboundRequest(
        clinic_id=FAKE_CLINIC_ID,
        message_id=uuid4(),
        conversation_id=uuid4(),
        channel=ChannelKind.ZALO_PERSONAL,
        external_ref=THREAD,
        text=text,
        proactive=proactive,
        account_id=account_id,
        sender_type=SenderType.STAFF,
        sender_user_id=OPERATOR_A,
    )


def ctx() -> ActionContext:
    return ActionContext(clinic_id=FAKE_CLINIC_ID, actor_type=ActorType.SYSTEM)


def build_delivery(
    table: Identities, clock: FakeTime, *accounts: str
) -> tuple[RegistryOutboundDelivery, dict[str, FakeChannel]]:
    store = InMemoryAccountStore(
        *(fake_account_config(id=name, label=name, channel=ChannelKind.ZALO_PERSONAL) for name in accounts)
    )
    registry = InMemoryChannelRegistry()
    channels = {name: make_channel(name) for name in accounts}
    for channel in channels.values():
        registry.register(FAKE_CLINIC_ID, channel)
    queue = build_queue(table, clock)
    return RegistryOutboundDelivery(store, registry, None, queue), channels


async def test_a_reply_goes_out_through_the_identity_of_the_request_only() -> None:
    clock = FakeTime()
    table = Identities(identity("hoa"), identity("long"))
    delivery, channels = build_delivery(table, clock, "hoa", "long")

    result = await delivery.deliver(ctx(), request("long"))

    assert result.status is SendStatus.SENT
    assert channels["hoa"].sent == []
    assert [part.text for part in channels["long"].sent] == ["Đã duyệt: hẹn gặp chị lúc 9 giờ."]


async def test_the_external_message_id_of_the_adapter_is_returned() -> None:
    delivery, _ = build_delivery(Identities(identity("long")), FakeTime(), "long")

    result = await delivery.deliver(ctx(), request("long"))

    assert result.status is SendStatus.SENT
    assert result.external_message_id == "fake-1"


async def test_no_operator_name_or_signature_is_added_to_the_text() -> None:
    delivery, channels = build_delivery(Identities(identity("long")), FakeTime(), "long")
    text = "Dạ chị đến lúc 9 giờ nhé."

    await delivery.deliver(ctx(), request("long", text=text))

    assert [part.text for part in channels["long"].sent] == [text]  # byte for byte what was stored


async def test_an_internal_account_is_never_used_for_a_customer() -> None:
    table = Identities(identity("notifier", purpose=IdentityPurpose.INTERNAL))
    delivery, channels = build_delivery(table, FakeTime(), "notifier")

    by_identity = await delivery.deliver(ctx(), request("notifier"))
    by_kind = await delivery.deliver(ctx(), request(None))  # the search by kind skips it as well

    assert by_identity.status is SendStatus.REJECTED
    assert by_identity.error_code is ErrorCode.POLICY_DENIED
    assert by_kind.status is SendStatus.REJECTED
    assert by_kind.error_code is ErrorCode.CHANNEL_UNAVAILABLE
    assert channels["notifier"].sent == []


async def test_the_kill_switch_blocks_the_delivery_and_nothing_leaves() -> None:
    delivery, channels = build_delivery(Identities(identity("long", kill_switch=True)), FakeTime(), "long")

    result = await delivery.deliver(ctx(), request("long"))

    assert result.status is SendStatus.REJECTED
    assert result.error_code is ErrorCode.CHANNEL_KILL_SWITCH_ON
    assert channels["long"].sent == []


async def test_a_proactive_message_over_the_cap_is_rejected_and_a_reply_is_not() -> None:
    delivery, channels = build_delivery(Identities(identity("long", gap=(0, 0), cap=1)), FakeTime(), "long")

    first = await delivery.deliver(ctx(), request("long", proactive=True))
    second = await delivery.deliver(ctx(), request("long", proactive=True))
    reply = await delivery.deliver(ctx(), request("long", proactive=False))

    assert first.status is SendStatus.SENT
    assert second.status is SendStatus.REJECTED
    assert second.error_code is ErrorCode.CHANNEL_DAILY_CAP_REACHED
    assert reply.status is SendStatus.SENT
    assert len(channels["long"].sent) == 2


async def test_an_identity_that_is_not_running_is_unavailable_not_replaced_by_another() -> None:
    table = Identities(identity("hoa"), identity("long"))
    delivery, channels = build_delivery(table, FakeTime(), "hoa")  # "long" has no running channel

    result = await delivery.deliver(ctx(), request("long"))

    assert result.status is SendStatus.REJECTED
    assert result.error_code is ErrorCode.CHANNEL_UNAVAILABLE
    assert channels["hoa"].sent == []


# ------------------------------------------------- the agent's path through reply_target_from_channel
async def test_the_agent_reply_path_shares_the_gap_with_the_operators() -> None:
    clock = FakeTime()
    table = Identities(identity("long", gap=(7, 7)))
    queue = build_queue(table, clock)
    channel = make_channel("long")
    enqueue: EnqueueSend = immediate  # pyright: ignore[reportAssignmentType]

    # the agent answers through a target built the way the turn processor builds it
    target = reply_target_from_channel(
        channel, THREAD, ThreadKind.USER, f"long:{THREAD}", identity_queue=queue
    )
    await send_reply_in_parts(target, "Câu trả lời của trợ lý (mẫu).", enqueue_send=enqueue)
    await queue.send("long", sender(channel))  # an operator right after

    assert len(channel.sent) == 2
    assert clock.slept == [pytest.approx(7.0)]


async def test_an_installed_queue_is_used_when_no_queue_is_passed() -> None:
    clock = FakeTime()
    queue = build_queue(Identities(identity("long", kill_switch=True)), clock)
    channel = make_channel("long")
    install_identity_send_queue(queue)
    try:
        assert installed_identity_send_queue() is queue
        target = reply_target_from_channel(channel, THREAD, ThreadKind.USER, f"long:{THREAD}")
        result = await send_reply_in_parts(target, "Tin mẫu", enqueue_send=immediate)  # pyright: ignore[reportArgumentType]
    finally:
        install_identity_send_queue(None)

    assert result.sent_parts == 0
    assert channel.sent == []


async def test_send_reply_in_parts_keeps_the_external_ids_of_the_parts() -> None:
    channel = make_channel("long")
    target = reply_target_from_channel(channel, THREAD, ThreadKind.USER, f"long:{THREAD}")

    result = await send_reply_in_parts(target, "Tin mẫu", enqueue_send=immediate)  # pyright: ignore[reportArgumentType]

    assert result.external_message_ids == ["fake-1"]


def test_the_clinic_id_may_be_given_lazily() -> None:
    """The installation id is loaded after the wiring: the queue takes a callable as well."""
    table = Identities()
    holder: list[UUID] = []

    def clinic() -> UUID:
        holder.append(FAKE_CLINIC_ID)
        return FAKE_CLINIC_ID

    queue = IdentitySendQueue(clinic_id=clinic, lookup=table.lookup)

    assert queue is not None
    assert holder == []  # not read before the first send

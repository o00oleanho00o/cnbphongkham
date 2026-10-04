"""Which account sends an approved reply when a clinic runs several accounts of one channel kind (package G,
no TS source; closes an open item of ARCH-AI01 section 13).

Before: the first running account by id, whatever account had talked to the patient. Now: the account whose
``agent.threads`` row exists for the conversation's thread (the one that received the patient's messages), the
most recently active one when two know the patient, and the first by id only when no thread row tells.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pema.agent.testing import make_caps
from pema.channels.registry import InMemoryChannelRegistry
from pema.clinic.actions.outbound import OutboundRequest
from pema.composition.outbound import RegistryOutboundDelivery
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind, SendStatus
from pema_contracts.conversation import ThreadRow
from pema_contracts.errors import ErrorCode
from pema_contracts.roles import ActorType
from pema_contracts.testing import FAKE_CLINIC_ID, FakeChannel, InMemoryAccountStore, fake_account_config

THREAD = "synthetic-thread-1"
NOW = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)


class FakeThreads:
    def __init__(self, *rows: tuple[str, str, datetime | None]) -> None:
        self.rows = {(account, thread): at for account, thread, at in rows}

    async def get_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadRow | None:
        key = (account_id, thread_id)
        if key not in self.rows:
            return None
        return ThreadRow(
            account_id=account_id,
            thread_id=thread_id,
            thread_type=0,
            display_name="Người dùng mẫu",
            bot_enabled=True,
            message_count=1,
            last_message_at=self.rows[key],
        )


def _request() -> OutboundRequest:
    return OutboundRequest(
        clinic_id=FAKE_CLINIC_ID,
        message_id=uuid4(),
        conversation_id=uuid4(),
        channel=ChannelKind.ZALO_PERSONAL,
        external_ref=THREAD,
        text="Đã duyệt: hẹn gặp chị lúc 9 giờ.",
    )


def _ctx() -> ActionContext:
    return ActionContext(clinic_id=FAKE_CLINIC_ID, actor_type=ActorType.SYSTEM)


def _build(
    threads: FakeThreads | None, *, running: tuple[str, ...] = ("acc-a", "acc-b")
) -> tuple[RegistryOutboundDelivery, dict[str, FakeChannel]]:
    accounts = InMemoryAccountStore(
        fake_account_config(id="acc-a", label="Account A", channel=ChannelKind.ZALO_PERSONAL),
        fake_account_config(id="acc-b", label="Account B", channel=ChannelKind.ZALO_PERSONAL),
        fake_account_config(id="acc-c", label="Disabled", channel=ChannelKind.ZALO_PERSONAL, enabled=False),
    )
    registry = InMemoryChannelRegistry()
    channels = {name: FakeChannel(caps=make_caps(), account=name) for name in ("acc-a", "acc-b", "acc-c")}
    for name in running:
        registry.register(FAKE_CLINIC_ID, channels[name])
    return RegistryOutboundDelivery(accounts, registry, threads), channels


def _senders(channels: dict[str, FakeChannel]) -> list[str]:
    return [name for name, channel in channels.items() if channel.sent]


async def test_the_reply_goes_out_through_the_account_that_received_the_patient() -> None:
    """hai account cùng loại: tin đã duyệt đi bằng account đã nhận tin của bệnh nhân, không phải account đầu tiên"""
    delivery, channels = _build(FakeThreads(("acc-b", THREAD, NOW)))

    result = await delivery.deliver(_ctx(), _request())

    assert result.status is SendStatus.SENT
    assert _senders(channels) == ["acc-b"]


async def test_when_two_accounts_know_the_patient_the_most_recently_active_one_wins() -> None:
    """cả hai account đều có thread: chọn account hoạt động gần nhất"""
    delivery, channels = _build(
        FakeThreads(("acc-a", THREAD, NOW - timedelta(days=3)), ("acc-b", THREAD, NOW - timedelta(hours=1)))
    )
    await delivery.deliver(_ctx(), _request())
    assert _senders(channels) == ["acc-b"]

    delivery, channels = _build(
        FakeThreads(("acc-a", THREAD, NOW - timedelta(hours=1)), ("acc-b", THREAD, NOW - timedelta(days=3)))
    )
    await delivery.deliver(_ctx(), _request())
    assert _senders(channels) == ["acc-a"]


async def test_without_a_thread_row_it_falls_back_to_the_first_running_account_by_id() -> None:
    """không account nào có thread của bệnh nhân (hội thoại tạo tay): rơi về account chạy đầu tiên theo id"""
    delivery, channels = _build(FakeThreads(("acc-b", "another-thread", NOW)))
    await delivery.deliver(_ctx(), _request())
    assert _senders(channels) == ["acc-a"]


async def test_a_thread_of_an_account_that_is_not_running_does_not_attract_the_reply() -> None:
    """account có thread nhưng không chạy trong tiến trình này thì không được chọn (không gửi vào hư không)"""
    delivery, channels = _build(FakeThreads(("acc-b", THREAD, NOW)), running=("acc-a",))
    result = await delivery.deliver(_ctx(), _request())
    assert result.status is SendStatus.SENT
    assert _senders(channels) == ["acc-a"]


async def test_a_disabled_account_is_never_chosen_even_if_it_has_the_thread() -> None:
    """account tắt không bao giờ được chọn dù có thread"""
    delivery, channels = _build(FakeThreads(("acc-c", THREAD, NOW)), running=("acc-a", "acc-b", "acc-c"))
    await delivery.deliver(_ctx(), _request())
    assert _senders(channels) == ["acc-a"]


async def test_one_running_account_needs_no_thread_lookup_and_none_running_is_unavailable() -> None:
    """một account chạy: dùng luôn; không account nào chạy: bị từ chối CHANNEL_UNAVAILABLE"""

    class Exploding:
        async def get_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadRow | None:
            raise AssertionError("a single candidate must not trigger a lookup")

    delivery, channels = _build(Exploding(), running=("acc-b",))  # type: ignore[arg-type]
    assert (await delivery.deliver(_ctx(), _request())).status is SendStatus.SENT
    assert _senders(channels) == ["acc-b"]

    nobody, _ = _build(None, running=())
    result = await nobody.deliver(_ctx(), _request())
    assert result.status is SendStatus.REJECTED
    assert result.error_code is ErrorCode.CHANNEL_UNAVAILABLE

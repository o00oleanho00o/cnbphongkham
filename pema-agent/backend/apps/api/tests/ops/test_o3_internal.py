"""The internal notifier account: its guards, the linking code, and the Inbox guard (package O, step O3).

New tests (no zalo-agent original). No database: ``FakeInternalDirectory``, ``FakeChannel`` from the shared test
helpers, an in-memory registry and a fake link store. Covered: the internal sender refuses an account whose
purpose is not ``internal`` and a customer recipient, sends through ``channel.send_text`` (not proactive) and
never invents a recipient; the linking code is single use and expiring; a few wrong codes pause a sender; the
internal account never answers an unknown sender and never creates a conversation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_bot.nang_luc_kenh_bot import ZALO_BOT_CAPABILITIES
from pema.clinic.actions.notification_chain import LinkOutcome, code_hash, normalize_code
from pema.clinic.actions.notification_inbox import CODE_ALPHABET, CODE_LENGTH, display_code, new_link_code
from pema.notify.internal import InternalZaloSender
from pema.notify.link import (
    MAX_FAILURES,
    InternalAccountRegistry,
    InternalInboxGuard,
    LinkHandler,
    extract_codes,
)
from pema.notify.testing import FakeInternalDirectory, FakeInternalSender
from pema.notify.types import InternalTarget, InternalTargetKind
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind, InboundMessage, SendResult, SendStatus, ThreadKind
from pema_contracts.clinic_actions import InboxRef
from pema_contracts.errors import ErrorCode
from pema_contracts.roles import ActorType
from pema_contracts.testing import FakeChannel

CLINIC = UUID(int=1)
NOW = datetime(2026, 9, 20, 2, 0, tzinfo=UTC)
STAFF = InternalTarget(InternalTargetKind.STAFF, "zalo-op-fixture")
GROUP = InternalTarget(InternalTargetKind.GROUP, "group-fixture")


def sender_with(directory: FakeInternalDirectory | None = None) -> tuple[InternalZaloSender, FakeChannel]:
    channel = FakeChannel(caps=ZALO_BOT_CAPABILITIES, account="notifier")
    registry = InMemoryChannelRegistry()
    registry.register(CLINIC, channel)
    return InternalZaloSender(CLINIC, registry, directory or FakeInternalDirectory()), channel


# ------------------------------------------------------------------------------------- the guards
async def test_the_internal_account_sends_through_send_text_and_is_not_proactive() -> None:
    sender, channel = sender_with()
    assert (await sender.send(STAFF, "[Pema] hello")).status.value == "sent"
    assert (await sender.send(GROUP, "[Pema] group")).status.value == "sent"
    first, second = channel.sent
    assert (first.thread_id, first.proactive, first.thread_kind) == (
        "zalo-op-fixture",
        False,
        ThreadKind.USER,
    )
    assert second.thread_kind is ThreadKind.GROUP


async def test_an_account_that_is_not_internal_never_sends() -> None:
    sender, channel = sender_with(FakeInternalDirectory(purpose="customer"))
    result = await sender.send(STAFF, "x")
    assert result.error_code == "account_not_internal"
    assert channel.sent == []


async def test_the_internal_account_refuses_a_customer_recipient() -> None:
    sender, channel = sender_with(FakeInternalDirectory(customer_refs=frozenset({"zalo-op-fixture"})))
    result = await sender.send(STAFF, "x")
    assert result.error_code == "customer_recipient"
    assert result.retryable is False
    assert channel.sent == []


async def test_no_internal_account_skips_and_a_stopped_account_is_retryable() -> None:
    sender, _ = sender_with(FakeInternalDirectory(account_id=None))
    assert (await sender.send(STAFF, "x")).error_code == "no_internal_account"
    stopped = InternalZaloSender(CLINIC, InMemoryChannelRegistry(), FakeInternalDirectory())
    result = await stopped.send(STAFF, "x")
    assert (result.error_code, result.retryable) == ("account_not_running", True)


async def test_a_rejected_send_is_a_final_failure_with_the_code_of_the_channel() -> None:
    sender, channel = sender_with()
    channel.reject_with = SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.RATE_LIMITED)
    result = await sender.send(STAFF, "x")
    assert (result.error_code, result.retryable) == (ErrorCode.RATE_LIMITED.value, False)


# ------------------------------------------------------------------------------------ the code
def test_a_link_code_is_eight_unambiguous_characters_and_hash_only_is_stored() -> None:
    code = new_link_code()
    assert len(code) == CODE_LENGTH
    assert set(code) <= set(CODE_ALPHABET)
    assert not set("01OIL") & set(CODE_ALPHABET)
    shown = display_code(code)
    assert normalize_code(shown) == code
    assert code_hash(shown) == code_hash(code.lower())
    assert code not in code_hash(code)


def test_codes_are_found_in_a_chat_message() -> None:
    assert "ABCD2345" in extract_codes("pema abcd-2345 nhé")
    assert extract_codes("ABCD 2345") == ["ABCD2345"]
    assert extract_codes("xin chào") == []


# ------------------------------------------------------------------------------------ the handler
class FakeLinkStore:
    """Single use and expiry as the SQL does it: a code matches while unused and not expired."""

    def __init__(self) -> None:
        self.codes: dict[str, tuple[datetime, UUID, bool]] = {}
        self.linked: dict[UUID, str] = {}
        self.calls = 0

    def issue(self, code: str, user: UUID, expires: datetime) -> None:
        self.codes[code_hash(code)] = (expires, user, False)

    async def consume_link_code(self, code: str, zalo_user_id: str, at: datetime) -> LinkOutcome:
        self.calls += 1
        found = self.codes.get(code_hash(code))
        if found is None or found[2] or found[0] <= at:
            return LinkOutcome(linked=False, reason="unknown_or_expired")
        self.codes[code_hash(code)] = (found[0], found[1], True)
        self.linked[found[1]] = zalo_user_id
        return LinkOutcome(linked=True, user_id=found[1])


def message(text: str, sender: str = "zalo-op-fixture", *, account: str = "notifier") -> InboundMessage:
    return InboundMessage(
        channel=ChannelKind.ZALO_PERSONAL,
        account_id=account,
        update_id=uuid4().hex,
        thread_id=sender,
        sender_id=sender,
        sender_name="Người gửi mẫu",
        text=text,
        msg_id=uuid4().hex,
        sent_at=NOW,
    )


def handler(
    store: FakeLinkStore, replies: FakeInternalSender | None = None, clock: datetime = NOW
) -> LinkHandler:
    return LinkHandler(store, replies, clock=lambda: clock)


async def test_a_live_code_links_the_sender_once_and_is_confirmed_to_them() -> None:
    operator = uuid4()
    store, replies = FakeLinkStore(), FakeInternalSender()
    store.issue("ABCD2345", operator, NOW + timedelta(minutes=10))
    link = handler(store, replies)
    assert await link.handle(message("ABCD-2345"))
    assert store.linked == {operator: "zalo-op-fixture"}
    ((where, _),) = replies.sent
    assert (where.kind, where.ref) == (InternalTargetKind.STAFF, "zalo-op-fixture")
    # single use: the same code from anybody else does nothing
    assert not await link.handle(message("ABCD-2345", sender="zalo-other"))
    assert store.linked == {operator: "zalo-op-fixture"}


async def test_an_expired_code_does_not_link() -> None:
    store = FakeLinkStore()
    store.issue("ABCD2345", uuid4(), NOW + timedelta(minutes=10))
    late = handler(store, clock=NOW + timedelta(minutes=11))
    assert not await late.handle(message("ABCD2345"))
    assert store.linked == {}


async def test_a_wrong_code_gets_no_reply_and_a_burst_of_them_pauses_the_sender() -> None:
    store, replies = FakeLinkStore(), FakeInternalSender()
    link = handler(store, replies)
    for _ in range(MAX_FAILURES):
        assert not await link.handle(message("WXYZ-9999"))
    calls = store.calls
    assert not await link.handle(message("WXYZ-9999"))
    assert store.calls == calls  # paused: the store is not asked again
    assert replies.sent == []  # an unknown sender is never answered


async def test_a_group_message_never_links() -> None:
    store = FakeLinkStore()
    store.issue("ABCD2345", uuid4(), NOW + timedelta(minutes=10))
    group_message = message("ABCD2345").model_copy(update={"is_group": True})
    assert not await handler(store).handle(group_message)


# ------------------------------------------------------------------------------ the inbox guard
class RecordingInbox:
    def __init__(self) -> None:
        self.recorded: list[InboundMessage] = []

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        self.recorded.append(message)
        return InboxRef(conversation_id=uuid4())


def ctx() -> ActionContext:
    return ActionContext(clinic_id=CLINIC, actor_type=ActorType.SYSTEM)


async def test_a_message_to_the_internal_account_never_becomes_a_conversation() -> None:
    inner = RecordingInbox()
    registry = InternalAccountRegistry()
    registry.set_ids(frozenset({"notifier"}))
    seen: list[InboundMessage] = []

    async def on_message(_clinic: UUID, msg: InboundMessage) -> None:
        seen.append(msg)

    registry.handler = on_message
    guard = InternalInboxGuard(inner, registry)

    ref = await guard.record_inbound_message(ctx(), message("ABCD2345"))
    assert ref.duplicate  # the intake path stops here: no history row, no turn
    assert inner.recorded == []
    assert len(seen) == 1

    customer = await guard.record_inbound_message(ctx(), message("xin chào", account="long"))
    assert not customer.duplicate
    assert len(inner.recorded) == 1


async def test_without_a_handler_the_internal_message_is_dropped_not_recorded() -> None:
    inner = RecordingInbox()
    registry = InternalAccountRegistry()
    registry.set_ids(frozenset({"notifier"}))
    guard = InternalInboxGuard(inner, registry)
    assert (await guard.record_inbound_message(ctx(), message("hello"))).duplicate
    assert inner.recorded == []


async def test_the_registry_refreshes_from_its_loader_after_the_ttl() -> None:
    clock = [0.0]
    registry = InternalAccountRegistry(ttl_s=15.0, monotonic=lambda: clock[0])
    loads = [frozenset({"a"}), frozenset({"a", "b"})]

    async def load() -> frozenset[str]:
        return loads.pop(0)

    registry.loader = load
    await registry.ensure_fresh()
    assert registry.is_internal("a")
    assert not registry.is_internal("b")
    clock[0] = 5.0
    await registry.ensure_fresh()  # still fresh: no second load
    assert not registry.is_internal("b")
    clock[0] = 16.0
    await registry.ensure_fresh()
    assert registry.is_internal("b")

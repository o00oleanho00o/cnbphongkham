"""Outbound as the clinic identity, at the action layer (package O, step O4). New tests, no zalo-agent original.

Need ``PEMA_TEST_DATABASE_URL`` (the module is marked ``db``). They cover what happens before the network call:
the identity of the thread is resolved (its ``account_id``, else the channel's single customer account, else the
message stays ``queued`` with ``no_identity``), an internal account is never used, the sender is recorded and
passed on, the text is stored and sent exactly as typed (no signature), the adapter's ``external_message_id`` is
stored with ``status = sent`` (never ``delivered``), and a takeover between queue and send blocks the old
holder's queued message with ``thread_locked``. The queue, gap and cap are in ``test_o4_identity_queue.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import record_inbound
from pema.clinic.actions import FakeOutboundDelivery, assignment, conversations
from pema.clinic.actions.outbound import deliver_queued_message
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.conversations import MessageCreate, MessageStatus, SenderType
from pema_contracts.errors import ErrorCode
from pema_contracts.ops import TakeoverRequest

pytestmark = pytest.mark.db

TEXT = "Dạ chị đến lúc 9 giờ nhé."


def rows(admin: Engine, sql: str, **params: Any) -> list[Any]:
    with admin.connect() as conn:
        return list(conn.execute(text(sql), params).all())


async def new_thread(
    db: ClinicDatabase, admin: Engine, world: SeedResult, *, account: str | None = "long"
) -> UUID:
    ref = await record_inbound(
        db, world, uid=f"stranger-{uuid4().hex[:8]}", text="Em muốn đặt lịch (tin mẫu)"
    )
    if account is not None:
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.conversation SET account_id = :a WHERE id = :c"),
                {"a": account, "c": ref.conversation_id},
            )
    return ref.conversation_id


def real_like() -> FakeOutboundDelivery:
    """The fake with the opt-in the real delivery has: the action resolves the identity first."""
    return FakeOutboundDelivery(requires_identity=True)


async def test_the_request_carries_the_identity_the_sender_and_the_exact_text(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long", label="Long")
    cid = await new_thread(db, admin, world)
    delivery = real_like()

    sent = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    (request,) = delivery.requests
    assert request.account_id == "long"
    assert request.sender_type is SenderType.STAFF
    assert request.sender_user_id == world.users["cs.maianh"]
    assert request.text == TEXT  # no operator name, no signature
    assert sent.status is MessageStatus.SENT
    assert sent.sender_user_id == world.users["cs.maianh"]
    (body,) = rows(admin, "SELECT body FROM clinic.message WHERE id = :m", m=sent.id)
    assert body[0] == TEXT


async def test_the_external_message_id_is_stored_and_the_status_is_sent_never_delivered(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    cid = await new_thread(db, admin, world)
    delivery = real_like()
    delivery.result = SendResult(status=SendStatus.SENT, external_message_id="zalo-msg-4711")

    sent = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    ((external, status, sent_at),) = rows(
        admin, "SELECT external_message_id, status, sent_at FROM clinic.message WHERE id = :m", m=sent.id
    )
    assert external == "zalo-msg-4711"
    assert status == "sent"
    assert sent_at is not None
    assert "delivered" not in {member.value for member in MessageStatus}


async def test_no_identity_when_the_thread_has_no_account_and_the_channel_has_none(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    delivery = real_like()

    queued = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    assert queued.status is MessageStatus.QUEUED
    assert queued.error_code == ErrorCode.NO_IDENTITY.value
    assert delivery.requests == []  # nothing reached the channel


async def test_no_identity_when_the_channel_has_two_customer_accounts(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    add_account("hoa")
    cid = await new_thread(db, admin, world, account=None)
    delivery = real_like()

    queued = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    assert queued.status is MessageStatus.QUEUED
    assert queued.error_code == ErrorCode.NO_IDENTITY.value
    assert delivery.requests == []


async def test_a_single_customer_account_is_the_identity_of_a_thread_without_one(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    add_account("notifier", purpose="internal")  # an internal account does not count
    cid = await new_thread(db, admin, world, account=None)
    delivery = real_like()

    sent = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    assert sent.status is MessageStatus.SENT
    assert [r.account_id for r in delivery.requests] == ["long"]


async def test_an_internal_account_is_never_chosen_for_a_customer(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("notifier", purpose="internal")  # the only account of the channel
    cid = await new_thread(db, admin, world, account=None)
    delivery = real_like()

    queued = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    assert queued.status is MessageStatus.QUEUED
    assert queued.error_code == ErrorCode.NO_IDENTITY.value
    assert delivery.requests == []


async def test_a_takeover_between_queue_and_send_blocks_the_old_holders_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    cid = await new_thread(db, admin, world)
    first = staff_ctx("cs.maianh")
    second = staff_ctx("cs.thu")
    # the first operator's reply is stored and queued (no delivery yet): the reply is a claim
    queued = await conversations.send_message(db, first, cid, MessageCreate(text=TEXT), delivery=None)
    assert queued.status is MessageStatus.QUEUED
    await assignment.takeover(db, second, cid, TakeoverRequest(reason="Chị ấy gọi lại cho tôi (mẫu)"))
    delivery = real_like()

    blocked = await deliver_queued_message(db, first, queued.id, delivery)

    assert blocked is not None
    assert blocked.status is MessageStatus.REJECTED
    assert blocked.error_code == ErrorCode.THREAD_LOCKED.value
    assert delivery.requests == []


async def test_the_holders_own_queued_message_still_goes_out(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    cid = await new_thread(db, admin, world)
    first = staff_ctx("cs.maianh")
    queued = await conversations.send_message(db, first, cid, MessageCreate(text=TEXT), delivery=None)
    delivery = real_like()

    sent = await deliver_queued_message(db, first, queued.id, delivery)

    assert sent is not None
    assert sent.status is MessageStatus.SENT
    assert len(delivery.requests) == 1


async def test_a_message_is_not_sent_twice(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    cid = await new_thread(db, admin, world)
    ctx = staff_ctx("cs.maianh")
    delivery = real_like()
    sent = await conversations.send_message(db, ctx, cid, MessageCreate(text=TEXT), delivery=delivery)

    again = await deliver_queued_message(db, ctx, sent.id, delivery)

    assert again is not None
    assert again.status is MessageStatus.SENT
    assert len(delivery.requests) == 1


async def test_a_fake_without_the_opt_in_keeps_the_behaviour_before_o4(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)  # no identity anywhere
    delivery = FakeOutboundDelivery()

    sent = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text=TEXT), delivery=delivery
    )

    assert sent.status is MessageStatus.SENT
    assert [r.account_id for r in delivery.requests] == [None]

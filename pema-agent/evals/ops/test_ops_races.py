"""Race suite of the shared inbox (package O, step O7). New tests, no zalo-agent original.

They need ``PEMA_TEST_DATABASE_URL`` (a throwaway Postgres; skipped without it) and run the real actions of
packages O2 and O4 against it. Each test creates the race on purpose (``asyncio.gather``, a delivery that waits
on an event) and then asserts the invariants of ``PLAN-AI01-O`` section 6 twice: on what the calls answered and
on the rows left behind (``evals.ops.invariants``, SQL).

* five operators claim one thread at the same moment: one holder, four 409 ``thread_locked``;
* a takeover while a send is in flight: the send that already started finishes, the old holder's next send is
  refused, the new holder's goes out; a send that was only queued is rejected and never reaches the channel;
* the end of a shift while the operator is typing (a delivery in flight): the thread moves, the in-flight
  message finishes, the next one is refused;
* the same inbound webhook delivered several times at once: one message, one conversation, no change of holder;
* two devices of one operator: two claims leave one history row; the same send repeated with one
  ``Idempotency-Key`` is one message and ONE delivery (see the strict ``xfail`` there);
* two operators write the first reply to an unassigned thread together: one auto-claims, the other is refused;
* a load of threads with five operators racing on all of them (the claims part of the load eval, smaller).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from evals.ops.db_support import OPERATOR_KEYS, new_threads, staff_context
from evals.ops.invariants import all_invariants
from evals.ops.measure_claims import ClaimsParameters, measure_claims
from pema.api.clinic_testing import record_inbound
from pema.clinic.actions import _common, assignment, conversations, roster
from pema.clinic.actions.outbound import OutboundRequest, deliver_queued_message
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.common import VN_TZ
from pema_contracts.conversations import MessageCreate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import RosterEntryCreate, TakeoverRequest, Weekday

pytestmark = pytest.mark.db

MONDAY_10 = datetime(2026, 9, 21, 10, 0, tzinfo=VN_TZ)


# ------------------------------------------------------------------------------------------ helpers
def rows(admin: Engine, sql: str, **params: Any) -> list[Any]:
    with admin.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def holder_of(admin: Engine, conversation_id: UUID) -> UUID | None:
    (row,) = rows(admin, "SELECT assigned_user_id FROM clinic.conversation WHERE id = :c", c=conversation_id)
    return row[0]


def messages(admin: Engine, conversation_id: UUID) -> list[Any]:
    return rows(
        admin,
        "SELECT id, sender_user_id, sender_type, status, error_code, body FROM clinic.message "
        "WHERE conversation_id = :c AND direction = 'outbound' ORDER BY created_at, id",
        c=conversation_id,
    )


class GateDelivery:
    """An ``OutboundDelivery`` that can hold a send in flight: the request is recorded when ``deliver`` is
    entered, and ``deliver`` returns only after ``go`` is set (when ``hold`` is on)."""

    requires_identity = True

    def __init__(self, *, hold: bool = False) -> None:
        self.hold = hold
        self.entered = asyncio.Event()
        self.go = asyncio.Event()
        self.requests: list[OutboundRequest] = []

    async def deliver(self, ctx: ActionContext, request: OutboundRequest) -> SendResult:
        self.requests.append(request)
        self.entered.set()
        if self.hold:
            await self.go.wait()
        return SendResult(status=SendStatus.SENT, external_message_id=f"synthetic-{len(self.requests)}")


async def reply(
    db: ClinicDatabase,
    ctx: ActionContext,
    conversation_id: UUID,
    delivery: Any,
    body: str = "Dạ em chào chị ạ.",
) -> Any:
    return await conversations.send_message(
        db, ctx, conversation_id, MessageCreate(text=body), delivery=delivery
    )


async def refusal_of(call: Any) -> DomainError | None:
    try:
        await call
    except DomainError as exc:
        return exc
    return None


@pytest.fixture
def identity(add_account: Any, operators: None) -> str:
    return add_account("long", label="Long")


# --------------------------------------------------------------------------------------- 1. claims
async def test_five_operators_claim_one_thread_at_once_one_wins_and_four_are_told_who_holds_it(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    outcomes = await asyncio.gather(
        *(refusal_of(assignment.claim(db, staff_context(world, key), thread)) for key in OPERATOR_KEYS)
    )

    refused = [exc for exc in outcomes if exc is not None]
    assert len(refused) == len(OPERATOR_KEYS) - 1
    assert all(exc.code is ErrorCode.THREAD_LOCKED for exc in refused)
    assert all(" đang trả lời" in exc.message for exc in refused), "the loser is told who holds the thread"
    winner = holder_of(admin, thread)
    assert winner in {world.users[key] for key in OPERATOR_KEYS}
    (history,) = rows(
        admin, "SELECT kind, user_id FROM clinic.conversation_assignment WHERE conversation_id = :c", c=thread
    )
    assert (history.kind, history.user_id) == ("claim", winner)
    notices = rows(
        admin, "SELECT recipient_kind FROM clinic.notification_outbox WHERE conversation_id = :c", c=thread
    )
    assert [n.recipient_kind for n in notices] == ["team_group"], "one claim, one group notice, nothing else"
    assert all_invariants(admin, [thread]) == []


async def test_many_threads_claimed_by_five_operators_each_have_exactly_one_holder(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    threads = await new_threads(db, admin, world, 12)
    await asyncio.gather(
        *(
            refusal_of(assignment.claim(db, staff_context(world, key), thread))
            for thread in threads
            for key in OPERATOR_KEYS
        )
    )

    holders = [holder_of(admin, thread) for thread in threads]
    assert None not in holders
    versions = rows(
        admin, "SELECT assignment_version FROM clinic.conversation WHERE id = ANY(:ids)", ids=threads
    )
    assert {row.assignment_version for row in versions} == {2}, "one change per thread, whoever won"
    assert all_invariants(admin, threads) == []


# ------------------------------------------------------------------------ 2. takeover during a send
async def test_a_takeover_during_a_send_lets_the_send_finish_and_refuses_the_old_holders_next_one(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    old, new = staff_context(world, "cs.maianh"), staff_context(world, "cs.thu")
    await assignment.claim(db, old, thread)
    delivery = GateDelivery(hold=True)

    sending = asyncio.create_task(reply(db, old, thread, delivery, "Tin đang gửi"))
    await asyncio.wait_for(delivery.entered.wait(), timeout=30)
    await assignment.takeover(db, new, thread, TakeoverRequest(reason="Chị xin gặp người khác (mẫu)"))
    delivery.go.set()
    sent = await sending

    assert sent.status.value == "sent", "the send that had already started finishes"
    assert holder_of(admin, thread) == world.users["cs.thu"]
    after = await refusal_of(reply(db, old, thread, delivery, "Tin sau khi bị tiếp quản"))
    assert after is not None and after.code is ErrorCode.THREAD_LOCKED
    await reply(db, new, thread, delivery, "Em tiếp nhận ạ")
    assert [r.text for r in delivery.requests] == ["Tin đang gửi", "Em tiếp nhận ạ"]
    assert [r.sender_user_id for r in delivery.requests] == [world.users["cs.maianh"], world.users["cs.thu"]]
    assert all_invariants(admin, [thread]) == []


async def test_a_message_queued_before_the_takeover_never_reaches_the_channel(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    old, new = staff_context(world, "cs.maianh"), staff_context(world, "cs.thu")
    await assignment.claim(db, old, thread)
    queued = await conversations.send_message(db, old, thread, MessageCreate(text="Chờ gửi"), delivery=None)
    await assignment.takeover(db, new, thread, TakeoverRequest(reason="Đổi người (mẫu)"))
    delivery = GateDelivery()

    result = await deliver_queued_message(db, old, queued.id, delivery)

    assert result is not None
    assert (result.status.value, result.error_code) == ("rejected", "thread_locked")
    assert delivery.requests == [], "nothing reached the channel"
    assert all_invariants(admin, [thread]) == []


# ------------------------------------------------------------------------------ 3. end of the shift
async def test_the_end_of_a_shift_while_the_operator_is_typing_moves_the_thread_and_refuses_the_next_send(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    manager, mai = staff_context(world, "manager"), staff_context(world, "cs.maianh")
    await roster.create_entry(
        db,
        manager,
        RosterEntryCreate(
            account_id="long",
            user_id=world.users["cs.thu"],
            weekdays=[Weekday.MON],
            start="08:00",
            end="17:00",
        ),
    )
    await assignment.claim(db, mai, thread)
    delivery = GateDelivery(hold=True)

    typing = asyncio.create_task(reply(db, mai, thread, delivery, "Tin đang gửi lúc hết ca"))
    await asyncio.wait_for(delivery.entered.wait(), timeout=30)
    with _common.use_clock(lambda: MONDAY_10):
        moved = await assignment.end_shift(db, manager, world.users["cs.maianh"])
    delivery.go.set()
    sent = await typing

    assert (moved.rerouted, moved.to_queue, moved.skipped) == (1, 0, 0)
    assert sent.status.value == "sent", "the message that was being sent finishes"
    assert holder_of(admin, thread) == world.users["cs.thu"]
    after = await refusal_of(reply(db, mai, thread, delivery, "Tin sau hết ca"))
    assert after is not None and after.code is ErrorCode.THREAD_LOCKED
    kinds = [
        r.kind
        for r in rows(
            admin,
            'SELECT kind FROM clinic.conversation_assignment WHERE conversation_id = :c ORDER BY "at", id',
            c=thread,
        )
    ]
    assert kinds == ["claim", "shift_end"]
    assert all_invariants(admin, [thread]) == []


async def test_a_shift_end_and_a_claim_of_the_same_thread_at_once_leave_one_holder(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    manager, mai, thu = (staff_context(world, key) for key in ("manager", "cs.maianh", "cs.thu"))
    await assignment.claim(db, mai, thread)

    with _common.use_clock(lambda: MONDAY_10):
        results = await asyncio.gather(
            assignment.end_shift(db, manager, world.users["cs.maianh"]),
            refusal_of(assignment.claim(db, thu, thread)),
        )

    assert holder_of(admin, thread) in {None, world.users["cs.thu"]}
    assert results[0].rerouted + results[0].to_queue + results[0].skipped == 1
    assert all_invariants(admin, [thread]) == []


# --------------------------------------------------------------------------- 4. duplicate webhooks
async def test_the_same_inbound_webhook_delivered_five_times_at_once_is_one_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    thread_key, update_id, uid = uuid4().hex, uuid4().hex, f"stranger-{uuid4().hex[:8]}"
    first = await record_inbound(
        db, world, uid=uid, thread=thread_key, update_id=update_id, text="Em hỏi (tin mẫu)"
    )
    holder = staff_context(world, "cs.maianh")
    await assignment.claim(db, holder, first.conversation_id)

    refs = await asyncio.gather(
        *(
            record_inbound(
                db, world, uid=uid, thread=thread_key, update_id=update_id, text="Em hỏi (tin mẫu)"
            )
            for _ in range(5)
        )
    )

    assert all(ref.duplicate for ref in refs), "a repeat of an update id writes nothing"
    assert {ref.conversation_id for ref in refs} == {first.conversation_id}
    inbound = rows(
        admin,
        "SELECT count(*) AS n FROM clinic.message WHERE conversation_id = :c AND direction = 'inbound'",
        c=first.conversation_id,
    )
    assert inbound[0].n == 1
    assert holder_of(admin, first.conversation_id) == world.users["cs.maianh"], (
        "a duplicate never moves the holder"
    )
    history = rows(
        admin,
        "SELECT count(*) AS n FROM clinic.conversation_assignment WHERE conversation_id = :c",
        c=first.conversation_id,
    )
    assert history[0].n == 1
    assert all_invariants(admin, [first.conversation_id]) == []


async def test_the_same_inbound_webhook_arriving_for_the_first_time_five_times_at_once_is_one_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    thread_key, update_id, uid = uuid4().hex, uuid4().hex, f"stranger-{uuid4().hex[:8]}"

    refs = await asyncio.gather(
        *(
            record_inbound(
                db, world, uid=uid, thread=thread_key, update_id=update_id, text="Em hỏi (tin mẫu)"
            )
            for _ in range(5)
        )
    )

    assert sum(1 for ref in refs if not ref.duplicate) == 1, "exactly one of the five wrote the message"
    assert len({ref.conversation_id for ref in refs}) == 1
    count = rows(
        admin,
        "SELECT count(*) AS n FROM clinic.message WHERE conversation_id = :c AND direction = 'inbound'",
        c=refs[0].conversation_id,
    )
    assert count[0].n == 1


# --------------------------------------------------------------------------- 5. two devices, one operator
async def test_two_devices_of_one_operator_claiming_at_once_leave_one_history_row(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    me = staff_context(world, "cs.maianh")

    results = await asyncio.gather(assignment.claim(db, me, thread), assignment.claim(db, me, thread))

    assert [r.assigned_user_id for r in results] == [world.users["cs.maianh"]] * 2
    (count,) = rows(
        admin, "SELECT count(*) AS n FROM clinic.conversation_assignment WHERE conversation_id = :c", c=thread
    )
    assert count.n == 1, "claiming what you already hold changes nothing"
    assert all_invariants(admin, [thread]) == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "known gap, not fixed in O7: deliver_queued_message reads the status 'queued', releases the "
        "transaction, calls the channel, and only then writes 'sent'. A repeat of the same Idempotency-Key "
        "that arrives while the first call is in flight finds the same queued row and delivers it a second "
        "time. See SEC-64 in SECURITY-REVIEW-AI01 and the open items of the O7 report."
    ),
)
async def test_the_same_send_from_two_devices_with_one_idempotency_key_is_delivered_once(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    me = staff_context(world, "cs.maianh", idempotency_key="device-retry-1")
    await assignment.claim(db, me, thread)
    delivery = GateDelivery(hold=True)

    first = asyncio.create_task(reply(db, me, thread, delivery, "Gửi một lần thôi"))
    await asyncio.wait_for(delivery.entered.wait(), timeout=30)
    second = asyncio.create_task(reply(db, me, thread, delivery, "Gửi một lần thôi"))
    await asyncio.sleep(1)  # the second device's request reaches the delivery step while the first waits
    delivery.go.set()
    await asyncio.gather(first, second)

    stored = messages(admin, thread)
    assert len(stored) == 1, "one Idempotency-Key is one message"
    assert len(delivery.requests) == 1, "and one delivery to the customer"


async def test_the_same_send_repeated_after_it_finished_is_not_delivered_again(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    me = staff_context(world, "cs.maianh", idempotency_key="device-retry-2")
    delivery = GateDelivery()

    one = await reply(db, me, thread, delivery, "Gửi một lần")
    two = await reply(db, me, thread, delivery, "Gửi một lần")

    assert one.id == two.id
    assert len(messages(admin, thread)) == 1
    assert len(delivery.requests) == 1


# ----------------------------------------------------------------------- 6. first reply of two operators
async def test_two_operators_writing_the_first_reply_together_one_claims_and_the_other_is_refused(
    db: ClinicDatabase, admin: Engine, world: SeedResult, identity: str
) -> None:
    (thread,) = await new_threads(db, admin, world, 1)
    delivery = GateDelivery()
    mai, thu = staff_context(world, "cs.maianh"), staff_context(world, "cs.thu")

    outcomes = await asyncio.gather(
        refusal_of(reply(db, mai, thread, delivery, "Mai Anh trả lời")),
        refusal_of(reply(db, thu, thread, delivery, "Thu trả lời")),
    )

    refused = [exc for exc in outcomes if exc is not None]
    assert len(refused) == 1 and refused[0].code is ErrorCode.THREAD_LOCKED
    assert len(delivery.requests) == 1, "only the holder's message reached the customer"
    (sent,) = messages(admin, thread)
    assert sent.sender_user_id == holder_of(admin, thread)
    assert all_invariants(admin, [thread]) == []


# --------------------------------------------------------------------------------- 7. a load of races
async def test_five_operators_racing_on_thirty_threads_leave_every_invariant_intact(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    report = await measure_claims(db, admin, world, ClaimsParameters(threads=30, takeover_every=5))

    assert report.violations == ()
    assert report.claims_won == 30
    assert report.claims_locked == report.claim_attempts - report.claims_won - sum(
        report.other_errors.values()
    )
    assert report.other_errors == {}
    assert report.threads_with_one_holder == 30
    assert report.delivered_to_channel == report.sends, "every stored reply reached the channel once"

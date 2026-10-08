"""Assignment history, claim, send lock, takeover, release, assign, end of shift (package O, step O2).

New tests (no zalo-agent original). Need ``PEMA_TEST_DATABASE_URL`` (the module is marked ``db``). They cover the
acceptance of the recipe: one holder per thread, a history row for every kind, 409 ``thread_locked`` on a send by a non-holder, release from the
STAFF state calls package M's port (a fake), RBAC denials for the accountant and reception, audit rows, and the
races (two claims at once, a takeover during a send, a shift end with a message still queued).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from itertools import pairwise
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import record_inbound
from pema.clinic.actions import FakeOutboundDelivery, _common, assignment, conversations, roster
from pema.clinic.actions.assignment import CareHandbackRefusedError
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.common import VN_TZ
from pema_contracts.conversations import ConversationStatus, ConversationUpdate, MessageCreate, MessageStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import (
    AssignmentKind,
    AssignRequest,
    ReleaseRequest,
    RosterEntryCreate,
    TakeoverRequest,
    Weekday,
)

pytestmark = pytest.mark.db

MONDAY_10 = datetime(2026, 9, 21, 10, 0, tzinfo=VN_TZ)
PAYLOAD_KEYS = {
    "event",
    "short_code",
    "identity_label",
    "urgency",
    "summary",
    "deep_link",
    "from_user_id",
    "to_user_id",
}


# ------------------------------------------------------------------------------------------ helpers
def rows(admin: Engine, sql: str, **params: Any) -> list[Any]:
    with admin.connect() as conn:
        return list(conn.execute(text(sql), params).all())


def history(admin: Engine, conversation_id: UUID) -> list[Any]:
    return rows(
        admin,
        'SELECT kind, user_id, previous_user_id, reason, "by" FROM clinic.conversation_assignment '
        'WHERE conversation_id = :c ORDER BY "at", id',
        c=conversation_id,
    )


def holder_of(admin: Engine, conversation_id: UUID) -> UUID | None:
    (row,) = rows(admin, "SELECT assigned_user_id FROM clinic.conversation WHERE id = :c", c=conversation_id)
    return row[0]


async def new_thread(
    db: ClinicDatabase,
    admin: Engine,
    world: SeedResult,
    *,
    account: str | None = "long",
    linked: bool = True,
) -> UUID:
    """A conversation of the synthetic patient P025 (or of an unlinked customer), tied to an identity."""
    uid = "demo-uid-025" if linked else f"stranger-{uuid4().hex[:8]}"
    ref = await record_inbound(db, world, uid=uid, text="Em muốn hỏi về lịch tái khám (tin mẫu)")
    if account is not None:
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.conversation SET account_id = :a WHERE id = :c"),
                {"a": account, "c": ref.conversation_id},
            )
    return ref.conversation_id


class FakeCare:
    """The ``CareHandback`` seam with package M's STAFF state under the test's control."""

    def __init__(self, *, staff_state: bool = True, refuses: bool = False) -> None:
        self.staff_state = staff_state
        self.refuses = refuses
        self.released: list[tuple[UUID, str]] = []

    async def is_staff_state(self, ctx: ActionContext, patient_id: UUID) -> bool:
        return self.staff_state

    async def release_to_auto(self, ctx: ActionContext, patient_id: UUID, note: str) -> None:
        if self.refuses:
            raise CareHandbackRefusedError("InvalidTransitionError")
        self.released.append((patient_id, note))


class GateDelivery:
    """A delivery that stops inside ``deliver`` until the test opens the gate (a send "in flight")."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    async def deliver(self, ctx: ActionContext, request: Any) -> SendResult:
        self.entered.set()
        await self.gate.wait()
        return SendResult(status=SendStatus.SENT, external_message_id="gate-1")


# ------------------------------------------------------------------------------------------ claim
async def test_a_claim_takes_an_unassigned_thread_and_writes_everything_that_goes_with_it(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long", label="Long")
    cid = await new_thread(db, admin, world)
    mai = staff_ctx("cs.maianh")
    out = await assignment.claim(db, mai, cid)
    assert out.assigned_user_id == world.users["cs.maianh"]
    assert out.assigned_user_name
    assert out.assignment_version == 2

    (entry,) = history(admin, cid)
    assert (entry.kind, entry.user_id, entry.previous_user_id, entry.by) == (
        "claim",
        world.users["cs.maianh"],
        None,
        world.users["cs.maianh"],
    )
    audit = rows(
        admin,
        "SELECT details FROM clinic.audit_log WHERE action = 'thread.claim' AND entity_id = :c",
        c=str(cid),
    )
    assert len(audit) == 1
    assert audit[0][0]["kind"] == "claim"


async def test_claiming_what_you_already_hold_changes_nothing(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    mai = staff_ctx("cs.maianh")
    await assignment.claim(db, mai, cid)
    again = await assignment.claim(db, mai, cid)
    assert again.assignment_version == 2
    assert len(history(admin, cid)) == 1


async def test_a_thread_somebody_else_holds_cannot_be_claimed(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    with pytest.raises(DomainError) as err:
        await assignment.claim(db, staff_ctx("cs.thu"), cid)
    assert err.value.code is ErrorCode.THREAD_LOCKED
    assert err.value.message.endswith("đang trả lời — Tiếp quản?")
    assert (err.value.details or {})["holder_user_id"] == str(world.users["cs.maianh"])
    assert holder_of(admin, cid) == world.users["cs.maianh"]
    assert len(history(admin, cid)) == 1


async def test_two_claims_at_once_one_wins_and_the_other_gets_a_409(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    results = await asyncio.gather(
        assignment.claim(db, staff_ctx("cs.maianh"), cid),
        assignment.claim(db, staff_ctx("cs.thu"), cid),
        return_exceptions=True,
    )
    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, DomainError)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0].code in (ErrorCode.THREAD_LOCKED, ErrorCode.VERSION_CONFLICT)
    assert losers[0].http_status == 409
    (entry,) = history(admin, cid)
    assert holder_of(admin, cid) == entry.user_id, "one holder, and it is the one the history names"


async def test_a_stale_assignment_version_is_a_409(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    from pema_contracts.ops import ClaimRequest

    cid = await new_thread(db, admin, world, account=None)
    with pytest.raises(DomainError) as err:
        await assignment.claim(db, staff_ctx("cs.maianh"), cid, ClaimRequest(assignment_version=7))
    assert err.value.code is ErrorCode.VERSION_CONFLICT
    assert holder_of(admin, cid) is None


# ---------------------------------------------------------------------------------------- takeover


async def test_the_reason_of_a_takeover_never_reaches_the_audit_row(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    await assignment.takeover(db, staff_ctx("cs.thu"), cid, TakeoverRequest(reason="Lý do riêng tư (mẫu)"))
    (row,) = rows(
        admin,
        "SELECT details FROM clinic.audit_log WHERE action = 'thread.takeover' AND entity_id = :c",
        c=str(cid),
    )
    details = row[0]
    assert details["has_reason"] is True
    assert details["previous_user_id"] == str(world.users["cs.maianh"])
    assert "Lý do riêng tư" not in json.dumps(details, ensure_ascii=False)


async def test_a_takeover_needs_a_holder_who_is_somebody_else(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    request = TakeoverRequest(reason="Cần trả lời gấp")
    with pytest.raises(DomainError) as nobody:
        await assignment.takeover(db, staff_ctx("cs.thu"), cid, request)
    assert nobody.value.code is ErrorCode.INVALID_STATE
    await assignment.claim(db, staff_ctx("cs.thu"), cid)
    with pytest.raises(DomainError) as mine:
        await assignment.takeover(db, staff_ctx("cs.thu"), cid, request)
    assert mine.value.code is ErrorCode.INVALID_STATE
    assert [h.kind for h in history(admin, cid)] == ["claim"]


async def test_a_takeover_with_a_stale_version_is_refused(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    with pytest.raises(DomainError) as err:
        await assignment.takeover(
            db, staff_ctx("cs.thu"), cid, TakeoverRequest(reason="Cần trả lời", assignment_version=1)
        )
    assert err.value.code is ErrorCode.VERSION_CONFLICT
    assert holder_of(admin, cid) == world.users["cs.maianh"]


# ----------------------------------------------------------------------------------------- release
async def test_release_puts_the_thread_back_in_the_queue_and_only_the_holder_or_a_manager_may(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    with pytest.raises(DomainError) as err:
        await assignment.release(db, staff_ctx("cs.thu"), cid)
    assert err.value.code is ErrorCode.THREAD_LOCKED
    out = await assignment.release(db, staff_ctx("cs.maianh"), cid)
    assert out.assigned_user_id is None
    assert history(admin, cid)[-1].kind == "release"
    assert history(admin, cid)[-1].previous_user_id == world.users["cs.maianh"]
    # nothing to release now: a no-op, not an error
    again = await assignment.release(db, staff_ctx("cs.maianh"), cid)
    assert again.assignment_version == out.assignment_version
    # the thread can be claimed again by someone else
    await assignment.claim(db, staff_ctx("cs.thu"), cid)
    assert holder_of(admin, cid) == world.users["cs.thu"]
    # a manager releases a thread somebody else holds
    freed = await assignment.release(db, staff_ctx("manager"), cid)
    assert freed.assigned_user_id is None


async def test_a_release_to_the_agent_calls_package_m_and_frees_the_thread(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    mai = staff_ctx("cs.maianh")
    await assignment.claim(db, mai, cid)
    care = FakeCare(staff_state=True)
    out = await assignment.release(
        db, mai, cid, ReleaseRequest(to_agent=True, note="Khách đã yên tâm"), care=care
    )
    assert out.assigned_user_id is None
    assert care.released == [(world.patients["P025"], "Khách đã yên tâm")]


async def test_a_release_to_the_agent_is_refused_outside_the_staff_state_and_changes_nothing(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    mai = staff_ctx("cs.maianh")
    await assignment.claim(db, mai, cid)
    request = ReleaseRequest(to_agent=True)

    care = FakeCare(staff_state=False)
    with pytest.raises(DomainError) as not_staff:
        await assignment.release(db, mai, cid, request, care=care)
    assert not_staff.value.code is ErrorCode.INVALID_STATE
    assert care.released == []

    with pytest.raises(DomainError) as unwired:
        await assignment.release(db, mai, cid, request, care=None)
    assert unwired.value.code is ErrorCode.NOT_IMPLEMENTED

    refusing = FakeCare(staff_state=True, refuses=True)
    with pytest.raises(DomainError) as refused:
        await assignment.release(db, mai, cid, request, care=refusing)
    assert refused.value.code is ErrorCode.INVALID_STATE
    assert holder_of(admin, cid) == world.users["cs.maianh"], "M refused: the local release was rolled back"
    assert [h.kind for h in history(admin, cid)] == ["claim"]

    unlinked = await new_thread(db, admin, world, account=None, linked=False)
    await assignment.claim(db, mai, unlinked)
    with pytest.raises(DomainError) as no_patient:
        await assignment.release(db, mai, unlinked, request, care=FakeCare())
    assert no_patient.value.code is ErrorCode.INVALID_STATE


# ------------------------------------------------------------------------------------------ assign
async def test_a_manager_puts_a_colleague_on_a_thread_and_can_take_it_off_again(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    manager = staff_ctx("manager")
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    out = await assignment.assign(db, manager, cid, AssignRequest(user_id=world.users["cs.thu"]))
    assert out.assigned_user_id == world.users["cs.thu"]
    last = history(admin, cid)[-1]
    assert (last.kind, last.previous_user_id, last.by) == (
        "assign",
        world.users["cs.maianh"],
        world.users["manager"],
    )
    same = await assignment.assign(db, manager, cid, AssignRequest(user_id=world.users["cs.thu"]))
    assert same.assignment_version == out.assignment_version, "assigning the holder again is a no-op"
    freed = await assignment.assign(db, manager, cid, AssignRequest(user_id=None))
    assert freed.assigned_user_id is None


async def test_only_an_assignable_active_colleague_can_be_put_on_a_thread(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    for key in ("reception.lan", "accountant.hoa"):
        with pytest.raises(DomainError) as err:
            await assignment.assign(db, staff_ctx("manager"), cid, AssignRequest(user_id=world.users[key]))
        assert err.value.code is ErrorCode.VALIDATION_FAILED
    with pytest.raises(DomainError) as unknown:
        await assignment.assign(db, staff_ctx("manager"), cid, AssignRequest(user_id=uuid4()))
    assert unknown.value.code is ErrorCode.VALIDATION_FAILED
    assert history(admin, cid) == []


async def test_the_phu_trach_box_goes_through_the_assignment_core(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    mai, thu, manager = staff_ctx("cs.maianh"), staff_ctx("cs.thu"), staff_ctx("manager")
    current = await conversations.get_conversation(db, mai, cid)
    out = await conversations.update_conversation(
        db, mai, cid, ConversationUpdate(version=current.version, assigned_user_id=world.users["cs.maianh"])
    )
    assert out.assignment_version == 2
    (entry,) = history(admin, cid)
    assert entry.kind == "assign"
    # a colleague cannot take a thread someone holds through the box; a manager can
    with pytest.raises(DomainError) as err:
        await conversations.update_conversation(
            db, thu, cid, ConversationUpdate(version=out.version, assigned_user_id=world.users["cs.thu"])
        )
    assert err.value.code is ErrorCode.THREAD_LOCKED
    moved = await conversations.update_conversation(
        db, manager, cid, ConversationUpdate(version=out.version, assigned_user_id=world.users["cs.thu"])
    )
    assert moved.assigned_user_id == world.users["cs.thu"]
    # a status change alone is not an assignment
    count = len(history(admin, cid))
    await conversations.update_conversation(
        db, manager, cid, ConversationUpdate(version=moved.version, status=ConversationStatus.CLOSED)
    )
    assert len(history(admin, cid)) == count


# ------------------------------------------------------------------------------------- the send lock
async def test_only_the_holder_sends_and_the_refusal_names_the_holder(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    delivery = FakeOutboundDelivery()
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    sent = await conversations.send_message(
        db, staff_ctx("cs.maianh"), cid, MessageCreate(text="Chào bạn (tin mẫu)"), delivery=delivery
    )
    assert sent.status is MessageStatus.SENT
    with pytest.raises(DomainError) as err:
        await conversations.send_message(
            db, staff_ctx("cs.thu"), cid, MessageCreate(text="Xin chào (tin mẫu)"), delivery=delivery
        )
    assert err.value.code is ErrorCode.THREAD_LOCKED
    assert err.value.http_status == 409
    assert err.value.message.endswith("đang trả lời — Tiếp quản?")
    assert len(delivery.requests) == 1
    assert (
        rows(
            admin,
            "SELECT count(*) FROM clinic.message WHERE conversation_id = :c AND direction = 'outbound'",
            c=cid,
        )[0][0]
        == 1
    )


async def test_the_first_reply_on_an_unassigned_thread_claims_it(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    thu = staff_ctx("cs.thu")
    await conversations.send_message(
        db, thu, cid, MessageCreate(text="Chào bạn (tin mẫu)"), delivery=FakeOutboundDelivery()
    )
    assert holder_of(admin, cid) == world.users["cs.thu"]
    assert [h.kind for h in history(admin, cid)] == ["claim"]
    with pytest.raises(DomainError) as err:
        await conversations.send_message(
            db, staff_ctx("cs.maianh"), cid, MessageCreate(text="Tôi trả lời nữa"), delivery=None
        )
    assert err.value.code is ErrorCode.THREAD_LOCKED


async def test_a_refused_send_does_not_claim_the_thread(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None, linked=False)
    with pytest.raises(DomainError):
        await conversations.send_message(
            db, staff_ctx("cs.thu"), cid, MessageCreate(text="Nhắc lịch", proactive=True), delivery=None
        )
    assert holder_of(admin, cid) is None
    assert history(admin, cid) == []


async def test_a_takeover_during_a_send_lets_the_send_finish_and_refuses_the_next_one(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    old, new = staff_ctx("cs.maianh"), staff_ctx("doctor.mai")
    await assignment.claim(db, old, cid)
    gate = GateDelivery()
    in_flight = asyncio.create_task(
        conversations.send_message(db, old, cid, MessageCreate(text="Đang gửi (tin mẫu)"), delivery=gate)
    )
    await asyncio.wait_for(gate.entered.wait(), timeout=10)
    await assignment.takeover(db, new, cid, TakeoverRequest(reason="Bác sĩ trả lời thay"))
    gate.gate.set()
    finished = await asyncio.wait_for(in_flight, timeout=10)
    assert finished.status is MessageStatus.SENT, "the send that had started finishes"
    with pytest.raises(DomainError) as err:
        await conversations.send_message(
            db, old, cid, MessageCreate(text="Tin kế tiếp"), delivery=FakeOutboundDelivery()
        )
    assert err.value.code is ErrorCode.THREAD_LOCKED
    sent = await conversations.send_message(
        db, new, cid, MessageCreate(text="Bác sĩ đây"), delivery=FakeOutboundDelivery()
    )
    assert sent.sender_user_id == world.users["doctor.mai"]


# ------------------------------------------------------------------------------------- end of shift
async def _on_duty(
    db: ClinicDatabase, manager: ActionContext, world: SeedResult, account: str, key: str
) -> None:
    await roster.create_entry(
        db,
        manager,
        RosterEntryCreate(
            account_id=account,
            user_id=world.users[key],
            weekdays=[Weekday.MON],
            start="08:00",
            end="17:00",
        ),
    )


async def test_end_shift_moves_each_active_thread_to_whoever_is_on_duty_or_back_to_the_queue(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long", label="Long")
    add_account("hoa", label="Hoa")
    manager, mai = staff_ctx("manager"), staff_ctx("cs.maianh")
    await _on_duty(db, manager, world, "long", "cs.thu")
    await _on_duty(db, manager, world, "long", "cs.maianh")  # ending their own shift: they leave the answer
    on_long = await new_thread(db, admin, world, account="long")
    on_hoa = await new_thread(db, admin, world, account="hoa")
    no_identity = await new_thread(db, admin, world, account=None)
    closed = await new_thread(db, admin, world, account="long")
    for cid in (on_long, on_hoa, no_identity, closed):
        await assignment.claim(db, mai, cid)
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.conversation SET status = 'closed' WHERE id = :c"), {"c": closed})

    with _common.use_clock(lambda: MONDAY_10):
        result = await assignment.end_shift(db, manager, world.users["cs.maianh"])

    assert (result.rerouted, result.to_queue, result.skipped) == (1, 2, 0)
    assert holder_of(admin, on_long) == world.users["cs.thu"]
    assert holder_of(admin, on_hoa) is None, "nobody is rostered for that identity"
    assert holder_of(admin, no_identity) is None, "no identity, no roster: back to the queue"
    assert holder_of(admin, closed) == world.users["cs.maianh"], "a closed thread is left alone"
    last = history(admin, on_long)[-1]
    assert (last.kind, last.previous_user_id, last.by) == (
        "shift_end",
        world.users["cs.maianh"],
        world.users["manager"],
    )


async def test_end_shift_balances_the_threads_between_the_operators_on_duty(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    manager = staff_ctx("manager")
    await _on_duty(db, manager, world, "long", "cs.thu")
    await _on_duty(db, manager, world, "long", "doctor.mai")
    threads = [await new_thread(db, admin, world, account="long") for _ in range(4)]
    for cid in threads:
        await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    busy = await new_thread(db, admin, world, account="long")
    await assignment.claim(db, staff_ctx("cs.thu"), busy)  # cs.thu already has one

    with _common.use_clock(lambda: MONDAY_10):
        result = await assignment.end_shift(db, manager, world.users["cs.maianh"])

    assert result.rerouted == 4
    holders = [holder_of(admin, cid) for cid in threads]
    thu, doctor = world.users["cs.thu"], world.users["doctor.mai"]
    assert set(holders) <= {thu, doctor}
    totals = (1 + holders.count(thu), holders.count(doctor))  # cs.thu already held one thread
    assert abs(totals[0] - totals[1]) <= 1, "the threads are balanced, the busier operator gets fewer"


async def test_end_shift_with_a_message_still_queued_moves_the_thread_and_refuses_the_old_holder_next(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    manager, mai = staff_ctx("manager"), staff_ctx("cs.maianh")
    await _on_duty(db, manager, world, "long", "cs.thu")
    cid = await new_thread(db, admin, world, account="long")
    await conversations.send_message(db, mai, cid, MessageCreate(text="Bản nháp đang chờ"), delivery=None)
    (queued,) = rows(
        admin,
        "SELECT status FROM clinic.message WHERE conversation_id = :c AND direction = 'outbound'",
        c=cid,
    )
    assert queued[0] == "queued"

    with _common.use_clock(lambda: MONDAY_10):
        result = await assignment.end_shift(db, manager, world.users["cs.maianh"])

    assert result.rerouted == 1
    assert holder_of(admin, cid) == world.users["cs.thu"]
    assert (
        rows(
            admin,
            "SELECT status FROM clinic.message WHERE conversation_id = :c AND direction = 'outbound'",
            c=cid,
        )[0][0]
        == "queued"
    ), "the open message is not touched"
    with pytest.raises(DomainError) as err:
        await conversations.send_message(
            db, mai, cid, MessageCreate(text="Tin kế tiếp"), delivery=FakeOutboundDelivery()
        )
    assert err.value.code is ErrorCode.THREAD_LOCKED


async def test_end_shift_knows_its_user_and_an_empty_shift_changes_nothing(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    manager = staff_ctx("manager")
    with pytest.raises(DomainError) as unknown:
        await assignment.end_shift(db, manager, uuid4())
    assert unknown.value.code is ErrorCode.NOT_FOUND
    empty = await assignment.end_shift(db, manager, world.users["cs.maianh"])
    assert (empty.rerouted, empty.to_queue, empty.skipped) == (0, 0, 0)


# --------------------------------------------------------------------------- history, RBAC, scope
async def test_every_kind_leaves_a_history_row_newest_first_with_names_and_one_holder_at_a_time(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
) -> None:
    add_account("long")
    manager, mai, thu = staff_ctx("manager"), staff_ctx("cs.maianh"), staff_ctx("cs.thu")
    await _on_duty(db, manager, world, "long", "doctor.mai")
    cid = await new_thread(db, admin, world, account="long")
    await assignment.claim(db, mai, cid)
    await assignment.takeover(db, thu, cid, TakeoverRequest(reason="Em nhận giúp chị"))
    await assignment.release(db, thu, cid)
    await assignment.assign(db, manager, cid, AssignRequest(user_id=world.users["cs.maianh"]))
    with _common.use_clock(lambda: MONDAY_10):
        await assignment.end_shift(db, manager, world.users["cs.maianh"])

    listed = await assignment.list_assignments(db, thu, cid)
    assert [e.kind for e in listed] == [
        AssignmentKind.SHIFT_END,
        AssignmentKind.ASSIGN,
        AssignmentKind.RELEASE,
        AssignmentKind.TAKEOVER,
        AssignmentKind.CLAIM,
    ]
    assert {e.kind for e in listed} == set(AssignmentKind)
    assert listed[0].user_name is not None
    assert listed[0].previous_user_name is not None
    assert listed[3].reason == "Em nhận giúp chị"
    assert listed[4].by == world.users["cs.maianh"]
    # the chain of holders is consistent: each row's previous is the row before's holder
    chronological = list(reversed(listed))
    for before, after in pairwise(chronological):
        assert after.previous_user_id == before.user_id
    assert holder_of(admin, cid) == chronological[-1].user_id


@pytest.mark.parametrize("key", ["accountant.hoa", "reception.lan"])
async def test_the_accountant_and_reception_cannot_hold_assign_or_end_a_shift(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any, key: str
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    ctx = staff_ctx(key)
    calls: list[Any] = [
        assignment.claim(db, ctx, cid),
        assignment.takeover(db, ctx, cid, TakeoverRequest(reason="Muốn xem")),
        assignment.release(db, ctx, cid),
        assignment.assign(db, ctx, cid, AssignRequest(user_id=world.users["cs.thu"])),
        assignment.end_shift(db, ctx, world.users["cs.maianh"]),
        assignment.list_assignments(db, ctx, cid),
    ]
    for call in calls:
        with pytest.raises(DomainError) as err:
            await call
        assert err.value.code is ErrorCode.FORBIDDEN
    assert holder_of(admin, cid) == world.users["cs.maianh"]


async def test_a_doctor_and_a_care_operator_cannot_assign_or_end_a_shift(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    for key in ("doctor.mai", "cs.maianh"):
        with pytest.raises(DomainError) as assign_err:
            await assignment.assign(db, staff_ctx(key), cid, AssignRequest(user_id=world.users["cs.thu"]))
        assert assign_err.value.code is ErrorCode.FORBIDDEN
        with pytest.raises(DomainError) as shift_err:
            await assignment.end_shift(db, staff_ctx(key), world.users["cs.thu"])
        assert shift_err.value.code is ErrorCode.FORBIDDEN


async def test_a_doctor_cannot_claim_a_thread_outside_their_patients(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    stranger = await new_thread(db, admin, world, account=None, linked=False)
    with pytest.raises(DomainError) as err:
        await assignment.claim(db, staff_ctx("doctor.mai"), stranger)
    assert err.value.code is ErrorCode.NOT_FOUND
    mine = await new_thread(db, admin, world, account=None)
    assert (await assignment.claim(db, staff_ctx("doctor.mai"), mine)).assigned_user_id == world.users[
        "doctor.mai"
    ]


async def test_every_change_writes_exactly_one_audit_row_with_ids_only(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    cid = await new_thread(db, admin, world, account=None)
    manager = staff_ctx("manager")
    await assignment.claim(db, staff_ctx("cs.maianh"), cid)
    await assignment.takeover(db, staff_ctx("cs.thu"), cid, TakeoverRequest(reason="Em nhận"))
    await assignment.release(db, staff_ctx("cs.thu"), cid)
    await assignment.assign(db, manager, cid, AssignRequest(user_id=world.users["cs.maianh"]))
    audit = rows(
        admin,
        "SELECT action, actor_user_id, details FROM clinic.audit_log "
        "WHERE entity_id = :c AND action LIKE 'thread.%' ORDER BY id",
        c=str(cid),
    )
    assert [a.action for a in audit] == ["thread.claim", "thread.takeover", "thread.release", "thread.assign"]
    assert audit[3].actor_user_id == world.users["manager"]
    for entry in audit:
        flat = json.dumps(entry.details, ensure_ascii=False)
        assert "Em nhận" not in flat
        assert set(entry.details) >= {"kind", "previous_user_id", "user_id", "assignment_version"}


# --------------------------------------------------------------------------------------------- HTTP
async def test_the_http_routes(
    client_factory: Any, db: ClinicDatabase, admin: Engine, world: SeedResult, app: Any
) -> None:
    app.state.outbound_delivery = FakeOutboundDelivery()
    cid = await new_thread(db, admin, world, account=None)
    base = f"/api/v1/conversations/{cid}"
    mai = await client_factory("cs.maianh")
    thu = await client_factory("cs.thu")
    manager = await client_factory("manager")
    reception = await client_factory("reception.lan")

    claimed = await mai.post(f"{base}/claim")
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body["assigned_user_id"] == str(world.users["cs.maianh"])
    assert body["assigned_user_name"]
    assert body["assignment_version"] == 2

    locked = await thu.post(f"{base}/claim")
    assert locked.status_code == 409
    error = locked.json()["error"]
    assert error["code"] == "thread_locked"
    assert error["message"].endswith("đang trả lời — Tiếp quản?")
    assert error["details"]["holder_user_id"] == str(world.users["cs.maianh"])
    assert error["details"]["assignment_version"] == 2

    refused_send = await thu.post(f"{base}/messages", json={"text": "Xin chào (tin mẫu)"})
    assert refused_send.status_code == 409
    assert refused_send.json()["error"]["code"] == "thread_locked"

    needs_reason = await thu.post(f"{base}/takeover", json={})
    assert needs_reason.status_code == 422
    taken = await thu.post(f"{base}/takeover", json={"reason": "Em nhận giúp chị", "assignment_version": 2})
    assert taken.status_code == 200, taken.text
    assert taken.json()["assigned_user_id"] == str(world.users["cs.thu"])

    sent = await thu.post(f"{base}/messages", json={"text": "Xin chào (tin mẫu)"})
    assert sent.status_code == 201, sent.text
    assert (await mai.post(f"{base}/messages", json={"text": "Còn tôi"})).status_code == 409

    listed = await mai.get(f"{base}/assignments")
    assert listed.status_code == 200
    assert [e["kind"] for e in listed.json()] == ["takeover", "claim"]
    assert listed.json()[0]["reason"] == "Em nhận giúp chị"

    assert (
        await thu.post(f"{base}/assign", json={"user_id": str(world.users["cs.maianh"])})
    ).status_code == 403
    assigned = await manager.post(f"{base}/assign", json={"user_id": str(world.users["cs.maianh"])})
    assert assigned.status_code == 200, assigned.text
    released = await mai.post(f"{base}/release", json={})
    assert released.status_code == 200
    assert released.json()["assigned_user_id"] is None
    no_care = await mai.post(f"{base}/release", json={"to_agent": True})
    assert no_care.status_code in (409, 501)

    assert (await reception.post(f"{base}/claim")).status_code == 403
    assert (await reception.get(f"{base}/assignments")).status_code == 403
    shift = await manager.post(f"/api/v1/staff/{world.users['cs.maianh']}/end-shift")
    assert shift.status_code == 200
    assert shift.json()["user_id"] == str(world.users["cs.maianh"])
    assert (await mai.post(f"/api/v1/staff/{world.users['cs.maianh']}/end-shift")).status_code == 403
    assert (await manager.post(f"/api/v1/staff/{uuid4()}/end-shift")).status_code == 404

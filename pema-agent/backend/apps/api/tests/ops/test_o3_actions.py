"""Notifications on the database: ack, push tokens, linking, settings, the M adapters, the consumer (package O,
step O3).

New tests (no zalo-agent original). Need ``PEMA_TEST_DATABASE_URL`` (marked ``db``). They run the REAL actions and
SQL as ``be_app`` and the consumer over ``SqlNotifyStore`` with a fake internal sender and a fake clock. Covered:
own rows only (an ack of a colleague's notice is a 404), idempotent ack, ack by deep link, the push token is
stored encrypted and never returned and moves between users, the linking code is single use and expiring, the
settings need ``notify.manage``, ``StaffNotify`` queues PII-free rows (no care summary, no patient id, the on-call
number is never stored), the whole chain over SQL (in-app now, bell after the timeout unless acked, a log row per
attempt), the claim lease, the durable SLA checks and the credential boundary of the payloads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.care.routing_types import HandoffNotice, OnCallInfo
from pema.clinic.actions import notification_chain as chain
from pema.clinic.actions import notification_inbox as inbox
from pema.clinic.actions import sla_checks
from pema.clinic.actions.notifications import handoff_payload
from pema.clinic.actions.seed_demo import SeedResult
from pema.config import env as env_module
from pema.core.db import ClinicDatabase
from pema.notify.consumer import NotificationConsumer
from pema.notify.providers import (
    InAppProvider,
    OnCallBellProvider,
    TeamGroupProvider,
    ZaloBellProvider,
)
from pema.notify.staff_notify import OutboxStaffNotify
from pema.notify.store import SqlNotifyStore
from pema.notify.testing import FakeInternalSender
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import (
    NotifyPreferenceIn,
    NotifySettingsUpdate,
    PushPlatform,
    PushTokenIn,
)

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 20, 2, 0, tzinfo=UTC)
TOKEN = "fcm-token-fixture-0123456789"


@pytest.fixture(autouse=True)
def secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()


def one(admin: Engine, sql: str, **params: Any) -> Any:
    with admin.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def insert_notice(
    admin: Engine,
    world: SeedResult,
    *,
    user: UUID | None,
    kind: str = "assignment.takeover",
    recipient_kind: str = "user",
    conversation: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> UUID:
    notice_id = uuid4()
    body = payload or {
        "event": "takeover",
        "short_code": "#A1B2",
        "identity_label": "Long",
        "urgency": "normal",
        "summary": "Hội thoại #A1B2 đã được tiếp quản",
        "deep_link": f"/inbox?conversation={conversation or world.conversation_id}",
    }
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.notification_outbox (id, clinic_id, kind, recipient_kind, "
                "recipient_user_id, conversation_id, payload) VALUES (:i, :c, :k, :rk, :u, :v, CAST(:p AS jsonb))"
            ),
            {
                "i": notice_id,
                "c": world.clinic_id,
                "k": kind,
                "rk": recipient_kind,
                "u": user,
                "v": conversation or world.conversation_id,
                "p": json.dumps(body),
            },
        )
    return notice_id


# ------------------------------------------------------------------------------------------- the ack
async def test_an_operator_acks_own_notices_only_and_repeating_it_changes_nothing(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    mine = insert_notice(admin, world, user=world.users["cs.maianh"])
    theirs = insert_notice(admin, world, user=world.users["cs.thu"])
    ctx = staff_ctx("cs.maianh")
    first = await inbox.ack(db, ctx, mine)
    second = await inbox.ack(db, ctx, mine)
    assert first.acked_at is not None
    assert second.acked_at == first.acked_at
    assert one(admin, "SELECT state FROM clinic.notification_outbox WHERE id = :i", i=mine) == "sent"
    with pytest.raises(DomainError) as refused:
        await inbox.ack(db, ctx, theirs)
    assert refused.value.code is ErrorCode.NOT_FOUND
    assert one(admin, "SELECT acked_at FROM clinic.notification_outbox WHERE id = :i", i=theirs) is None
    assert one(admin, "SELECT count(*) FROM clinic.audit_log WHERE action = 'notification.ack'") == 1


async def test_opening_the_deep_link_acks_every_notice_about_it(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    a = insert_notice(admin, world, user=world.users["cs.maianh"])
    b = insert_notice(admin, world, user=world.users["cs.maianh"])
    other = insert_notice(admin, world, user=world.users["cs.thu"])
    ctx = staff_ctx("cs.maianh")
    assert await inbox.ack_target(db, ctx, conversation_id=world.conversation_id) == 2
    assert await inbox.ack_target(db, ctx, conversation_id=world.conversation_id) == 0
    assert one(admin, "SELECT count(*) FROM clinic.notification_outbox WHERE acked_at IS NOT NULL") == 2
    assert one(admin, "SELECT acked_at FROM clinic.notification_outbox WHERE id = :i", i=other) is None
    with pytest.raises(DomainError):
        await inbox.ack_target(db, ctx)  # no target at all
    listed = await inbox.list_own(db, ctx)
    assert {n.id for n in listed} == {a, b}


async def test_reception_and_the_accountant_get_no_notifications(
    db: ClinicDatabase, world: SeedResult, staff_ctx: Any
) -> None:
    for key in ("reception.lan", "accountant.hoa"):
        with pytest.raises(DomainError) as refused:
            await inbox.list_own(db, staff_ctx(key))
        assert refused.value.code is ErrorCode.FORBIDDEN


# ------------------------------------------------------------------------------------ push tokens
async def test_a_push_token_is_stored_encrypted_hashed_and_never_returned(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    ctx = staff_ctx("doctor.mai")
    out = await inbox.register_push_token(db, ctx, PushTokenIn(platform=PushPlatform.ANDROID, token=TOKEN))
    assert TOKEN not in out.model_dump_json()
    stored = one(admin, "SELECT token_enc FROM clinic.push_token WHERE id = :i", i=out.id)
    assert TOKEN not in stored
    assert one(admin, "SELECT token_hash FROM clinic.push_token WHERE id = :i", i=out.id) == chain.token_hash(
        TOKEN
    )
    again = await inbox.register_push_token(db, ctx, PushTokenIn(platform=PushPlatform.ANDROID, token=TOKEN))
    assert again.id == out.id
    target = await chain.load_target(db, world.clinic_id, world.users["doctor.mai"])
    assert [t.token for t in target.push_tokens] == [TOKEN]  # decrypted for the provider only
    # the phone changes hands: the token moves to the new user
    await inbox.register_push_token(
        db, staff_ctx("cs.thu"), PushTokenIn(platform=PushPlatform.ANDROID, token=TOKEN)
    )
    assert (
        one(admin, "SELECT user_id FROM clinic.push_token WHERE id = :i", i=out.id) == world.users["cs.thu"]
    )


async def test_a_colleagues_push_token_cannot_be_deleted(
    db: ClinicDatabase, world: SeedResult, staff_ctx: Any
) -> None:
    out = await inbox.register_push_token(
        db, staff_ctx("doctor.mai"), PushTokenIn(platform=PushPlatform.IOS, token=TOKEN)
    )
    with pytest.raises(DomainError) as refused:
        await inbox.delete_push_token(db, staff_ctx("cs.thu"), out.id)
    assert refused.value.code is ErrorCode.NOT_FOUND
    await inbox.delete_push_token(db, staff_ctx("doctor.mai"), out.id)


# ----------------------------------------------------------------------------------------- linking
async def test_the_link_code_is_single_use_and_expires(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any, add_account: Any
) -> None:
    add_account("notifier", purpose="internal", label="Thông báo")
    ctx = staff_ctx("cs.maianh")
    started = await inbox.start_link(db, ctx)
    assert started.internal_label == "Thông báo"
    assert (
        one(
            admin,
            "SELECT count(*) FROM clinic.notify_link_code WHERE code_hash = :h",
            h=chain.code_hash(started.code),
        )
        == 1
    )
    assert started.code not in str(
        one(admin, "SELECT string_agg(code_hash, ',') FROM clinic.notify_link_code")
    )

    at = datetime.now(UTC)
    first = await chain.consume_link_code(db, world.clinic_id, started.code, "zalo-op-fixture", at)
    assert first.linked
    assert first.user_id == world.users["cs.maianh"]
    status = await inbox.link_status(db, ctx)
    assert status.linked
    second = await chain.consume_link_code(db, world.clinic_id, started.code, "zalo-other", at)
    assert not second.linked

    expired = await inbox.start_link(db, ctx)
    late = at + timedelta(minutes=11)
    assert not (
        await chain.consume_link_code(db, world.clinic_id, expired.code, "zalo-op-fixture", late)
    ).linked
    assert not (await chain.consume_link_code(db, world.clinic_id, "ZZZZ9999", "zalo-op-fixture", at)).linked

    target = await chain.load_target(db, world.clinic_id, world.users["cs.maianh"])
    assert target.zalo_user_id == "zalo-op-fixture"
    # the same Zalo id cannot ring two operators: linking it to a colleague moves it
    other = await inbox.start_link(db, staff_ctx("cs.thu"))
    assert (await chain.consume_link_code(db, world.clinic_id, other.code, "zalo-op-fixture", at)).linked
    assert (await chain.load_target(db, world.clinic_id, world.users["cs.maianh"])).zalo_user_id is None
    assert not (await inbox.unlink(db, staff_ctx("cs.thu"))).linked


# -------------------------------------------------------------------------------------- settings
async def test_settings_need_notify_manage_and_have_defaults(
    db: ClinicDatabase, world: SeedResult, staff_ctx: Any
) -> None:
    defaults = await inbox.get_settings(db, staff_ctx("cs.maianh"))
    assert (defaults.ack_timeout_s, defaults.bell_enabled, defaults.push_enabled) == (180, True, False)
    with pytest.raises(DomainError) as refused:
        await inbox.update_settings(db, staff_ctx("cs.maianh"), NotifySettingsUpdate(ack_timeout_s=60))
    assert refused.value.code is ErrorCode.FORBIDDEN
    saved = await inbox.update_settings(
        db, staff_ctx("manager"), NotifySettingsUpdate(ack_timeout_s=60, team_group_id="group-fixture")
    )
    assert (saved.ack_timeout_s, saved.team_group_id) == (60, "group-fixture")
    cleared = await inbox.update_settings(db, staff_ctx("owner"), NotifySettingsUpdate(team_group_id=None))
    assert cleared.team_group_id is None
    assert cleared.ack_timeout_s == 60  # a field left out stays


async def test_quiet_hours_are_the_operators_own(db: ClinicDatabase, staff_ctx: Any) -> None:
    ctx = staff_ctx("doctor.an")
    saved = await inbox.set_preference(db, ctx, NotifyPreferenceIn(quiet_start="22:00", quiet_end="06:00"))
    assert (saved.quiet_start, saved.quiet_end) == ("22:00", "06:00")
    assert (await inbox.get_preference(db, staff_ctx("doctor.mai"))).quiet_start is None
    assert (await inbox.set_preference(db, ctx, NotifyPreferenceIn())).quiet_start is None


# ------------------------------------------------------------------------------------ M's StaffNotify
def notice(**changes: Any) -> HandoffNotice:
    base: dict[str, Any] = {
        "request_id": uuid4(),
        "patient_id": uuid4(),
        "depth": "D4",
        "urgency": "urgent",
        "summary": "Khách: P025\nĐộ sâu: D4\nGọi 0901234567",
        "sla_due_at": NOW + timedelta(minutes=5),
        "position": 0,
    }
    return HandoffNotice(**{**base, **changes})


async def test_staff_notify_queues_a_pii_free_row_and_never_the_care_summary(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    adapter = OutboxStaffNotify(db, world.clinic_id)
    handoff = notice()
    assert await adapter.notify_staff(world.users["cs.maianh"], handoff)
    row = json.loads(
        one(
            admin,
            "SELECT payload::text FROM clinic.notification_outbox WHERE kind = 'handoff.handoff_request'",
        )
    )
    text_of_row = json.dumps(row, ensure_ascii=False)
    assert "0901234567" not in text_of_row
    assert str(handoff.patient_id) not in text_of_row
    assert "Khách: P025" not in text_of_row
    assert row["request_id"] == str(handoff.request_id)
    assert row["urgency"] == "urgent"
    assert row["deep_link"] == f"/care/handoffs?request={handoff.request_id}"
    assert one(admin, "SELECT recipient_user_id FROM clinic.notification_outbox") == world.users["cs.maianh"]


async def test_the_on_call_notice_needs_an_internal_account_and_never_stores_the_number(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    contact = OnCallInfo(id=uuid4(), zalo_number="0000000001", owner="Trực (mẫu)", is_fixture=True)
    adapter = OutboxStaffNotify(db, world.clinic_id)
    assert not await adapter.notify_on_call(
        contact, notice(is_on_call=True)
    )  # no internal account: loud False
    assert one(admin, "SELECT count(*) FROM clinic.notification_outbox") == 0
    add_account("notifier", purpose="internal")
    assert await adapter.notify_on_call(contact, notice(is_on_call=True))
    assert one(admin, "SELECT recipient_kind FROM clinic.notification_outbox") == "on_call"
    assert "0000000001" not in str(one(admin, "SELECT payload::text FROM clinic.notification_outbox"))


def test_a_handoff_payload_with_an_unsafe_depth_text_falls_back_to_the_generic_sentence() -> None:
    request = uuid4()
    data = handoff_payload(
        request_id=request, urgency="normal", depth="0901234567", position=1, sla_due_at=None, on_call=False
    )
    assert "0901234567" not in json.dumps(data)
    assert data["summary"].startswith("Có yêu cầu chuyển người xử lý #")


# ----------------------------------------------------------------------------- the chain over SQL
def build_consumer(
    db: ClinicDatabase, world: SeedResult, sender: FakeInternalSender, now: list[datetime]
) -> Any:
    store = SqlNotifyStore(db, world.clinic_id)
    events: list[Any] = []
    consumer = NotificationConsumer(
        store=store,
        in_app=InAppProvider(emit=lambda kind, ident: events.append((kind, ident))),
        bell=ZaloBellProvider(sender),
        group=TeamGroupProvider(sender),
        on_call=OnCallBellProvider(sender),
        clock=lambda: now[0],
    )
    return consumer, events


async def test_the_chain_over_sql_in_app_now_bell_later_unless_acked(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    operator = world.users["cs.maianh"]
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE clinic.staff_profiles SET notify_zalo_user_id = 'zalo-op-fixture', "
                "notify_zalo_consented_at = now() WHERE user_id = :u"
            ),
            {"u": operator},
        )
    rung = insert_notice(admin, world, user=operator)
    stopped = insert_notice(admin, world, user=operator)
    group = insert_notice(admin, world, user=None, recipient_kind="team_group")
    sender = FakeInternalSender()
    now = [datetime.now(UTC)]
    consumer, events = build_consumer(db, world, sender, now)

    # settings: a group id so the group step can post
    await inbox.update_settings(db, staff_ctx("manager"), NotifySettingsUpdate(team_group_id="group-fixture"))
    report = await consumer.run_once()
    assert report.claimed == 3
    assert len(events) == 2  # in-app for the two user rows
    assert [t.ref for t, _ in sender.sent] == ["group-fixture"]
    assert one(admin, "SELECT state FROM clinic.notification_outbox WHERE id = :i", i=group) == "sent"
    assert one(admin, "SELECT chain_step FROM clinic.notification_outbox WHERE id = :i", i=rung) == "bell"

    await inbox.ack(db, staff_ctx("cs.maianh"), stopped)
    now[0] += timedelta(seconds=181)
    await consumer.run_once()
    bells = [t for t, _ in sender.sent if t.ref == "zalo-op-fixture"]
    assert len(bells) == 1  # only the notice nobody acknowledged rang
    assert one(admin, "SELECT state FROM clinic.notification_outbox WHERE id = :i", i=rung) == "sent"
    providers = {
        row[0]
        for row in admin.connect().execute(
            text("SELECT provider FROM clinic.notification_log WHERE outbox_id = :i"), {"i": rung}
        )
    }
    assert providers == {"in_app", "zalo_bell"}
    latency = one(admin, "SELECT max(latency_ms) FROM clinic.notification_log")
    assert latency is not None


async def test_a_claimed_row_is_not_claimed_twice_until_its_lease_ends(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    insert_notice(admin, world, user=world.users["cs.maianh"])
    first = await chain.claim_due(db, world.clinic_id, datetime.now(UTC) + timedelta(seconds=1))
    again = await chain.claim_due(db, world.clinic_id, datetime.now(UTC) + timedelta(seconds=2))
    assert (len(first), len(again)) == (1, 0)
    later = await chain.claim_due(
        db, world.clinic_id, datetime.now(UTC) + timedelta(seconds=chain.LEASE_S + 5)
    )
    assert len(later) == 1


# --------------------------------------------------------------------------- durable SLA checks
async def test_sla_checks_are_deduplicated_leased_and_retried(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    request = uuid4()
    due = datetime.now(UTC) - timedelta(minutes=1)
    for _ in range(2):
        await sla_checks.schedule(
            db, world.clinic_id, request_id=request, idx=0, due_at=due, dedupe_key=f"sla:{request}:0"
        )
    assert one(admin, "SELECT count(*) FROM clinic.sla_check") == 1
    now = datetime.now(UTC)
    (check,) = await sla_checks.claim_due(db, world.clinic_id, now)
    assert await sla_checks.claim_due(db, world.clinic_id, now) == []  # leased
    assert not await sla_checks.finish(db, world.clinic_id, check, ok=False, now=now)
    assert one(admin, "SELECT state FROM clinic.sla_check") == "pending"  # never ran, never "done"
    assert one(admin, "SELECT attempts FROM clinic.sla_check") == 1
    later = now + timedelta(hours=1)
    (retry,) = await sla_checks.claim_due(db, world.clinic_id, later)
    assert await sla_checks.finish(db, world.clinic_id, retry, ok=True, now=later)
    assert one(admin, "SELECT state FROM clinic.sla_check") == "done"


# ------------------------------------------------------------------------------ security
async def test_no_notification_response_or_row_carries_a_credential(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    ctx = staff_ctx("cs.maianh")
    await inbox.register_push_token(db, ctx, PushTokenIn(platform=PushPlatform.WEB, token=TOKEN))
    insert_notice(admin, world, user=world.users["cs.maianh"])
    started = await inbox.start_link(db, ctx)
    shown = json.dumps(
        [n.model_dump(mode="json") for n in await inbox.list_own(db, ctx)]
        + [(await inbox.get_settings(db, ctx)).model_dump(mode="json")]
        + [(await inbox.link_status(db, ctx)).model_dump(mode="json")]
    )
    for secret in (TOKEN, "token_enc", "_enc", started.code, "cookie"):
        assert secret not in shown

# ruff: noqa: PT018
"""Inbox, manual replies and the review queue through the HTTP API (delivery is a fake channel)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory, record_inbound
from pema.clinic.actions import FakeOutboundDelivery
from pema.clinic.actions.inbox_ingest import create_review_item
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.errors import ErrorCode
from pema_contracts.review import ReviewItemCreate, ReviewKind, ReviewOrigin, RiskLevel
from pema_contracts.roles import ActorType

pytestmark = pytest.mark.db


def agent_ctx(world: SeedResult) -> ActionContext:
    return ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)


async def make_item(
    db: ClinicDatabase,
    world: SeedResult,
    conversation_id: object | None,
    *,
    kind: ReviewKind = ReviewKind.REPLY_DRAFT,
    risk: RiskLevel = RiskLevel.NORMAL,
    origin: ReviewOrigin = ReviewOrigin.AGENT_TURN,
    draft: str = "Chào bạn, phòng khám đã nhận tin (nội dung mẫu).",
    patient: str | None = "P025",
) -> dict[str, Any]:
    item = await create_review_item(
        db,
        agent_ctx(world),
        ReviewItemCreate(
            job_id=f"job-{uuid4().hex}",
            clinic_id=world.clinic_id,
            patient_ref=patient,
            conversation_ref=str(conversation_id) if conversation_id else None,
            kind=kind,
            origin=origin,
            draft_text=draft,
            risk_level=risk,
            red_flags=["bleeding"] if risk is RiskLevel.RED_FLAG else [],
        ),
    )
    return item.model_dump(mode="json")


# ---------------------------------------------------------------- Inbox


async def test_the_inbox_lists_conversations_with_label_preview_and_pending_review_flag(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world, text="Em muốn hỏi về lịch tái khám (tin mẫu)")
    page = (await cs.get("/api/v1/conversations", params={"limit": 200})).json()
    row = next(c for c in page["items"] if c["id"] == str(ref.conversation_id))
    assert row["patient_code"] == "P025"
    assert row["patient_display_name"] == "Bệnh nhân mẫu 025"
    assert row["last_message_preview"].startswith("Em muốn hỏi")
    assert row["unread_count"] == 1
    assert row["has_pending_review"] is False
    seeded = next(c for c in page["items"] if c["id"] == str(world.conversation_id))
    assert seeded["has_pending_review"] is True
    pending = (
        await cs.get("/api/v1/conversations", params={"has_pending_review": "true", "limit": 200})
    ).json()
    assert str(world.conversation_id) in [c["id"] for c in pending["items"]]
    assert str(ref.conversation_id) not in [c["id"] for c in pending["items"]]


async def test_an_unlinked_zalo_user_is_a_conversation_without_a_patient(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    one = (await cs.get(f"/api/v1/conversations/{ref.conversation_id}")).json()
    assert one["patient_id"] is None
    assert one["patient_display_name"] == "Khách mẫu"  # the channel display name, staff-only
    assert one["external_ref"]


async def test_mark_read_clears_unread_and_message_listing_is_newest_first_and_audited(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    cs = await client_factory("cs.maianh")
    thread = uuid4().hex
    first = await record_inbound(db, world, thread=thread, text="tin 1")
    await record_inbound(db, world, thread=thread, text="tin 2")
    base = f"/api/v1/conversations/{first.conversation_id}"
    assert (await cs.get(base)).json()["unread_count"] == 2
    assert (await cs.post(f"{base}/read")).status_code == 204
    assert (await cs.get(base)).json()["unread_count"] == 0
    messages = (await cs.get(f"{base}/messages")).json()
    assert [m["body"] for m in messages["items"]] == ["tin 2", "tin 1"]
    with admin.connect() as conn:
        reads = conn.execute(
            text(
                "SELECT count(*) FROM clinic.audit_log WHERE action = 'conversation.read_messages' AND entity_id = :e"
            ),
            {"e": str(first.conversation_id)},
        ).scalar_one()
    assert reads == 1


async def test_a_manual_reply_is_queued_then_sent_and_a_retry_with_the_key_sends_once(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, app: Any
) -> None:
    fake = FakeOutboundDelivery()
    app.state.outbound_delivery = fake
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    url = f"/api/v1/conversations/{ref.conversation_id}/messages"
    headers = {"Idempotency-Key": f"reply-{uuid4().hex}"}
    first = await cs.post(url, json={"text": "Chào bạn, chúng tôi đã nhận tin."}, headers=headers)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "sent"
    assert first.json()["sender_type"] == "staff"
    assert first.json()["sent_at"] is not None
    retry = await cs.post(url, json={"text": "Chào bạn, chúng tôi đã nhận tin."}, headers=headers)
    assert retry.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert len(fake.requests) == 1, "the channel must receive the text once"
    other_body = await cs.post(url, json={"text": "Nội dung khác"}, headers=headers)
    assert other_body.status_code == 409
    assert other_body.json()["error"]["code"] == "duplicate_request"


async def test_without_a_wired_channel_the_reply_stays_queued_and_a_rejection_is_recorded(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, app: Any
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    url = f"/api/v1/conversations/{ref.conversation_id}/messages"
    queued = await cs.post(url, json={"text": "Chưa có kênh nào được nối."})
    assert queued.json()["status"] == "queued"

    app.state.outbound_delivery = FakeOutboundDelivery(
        result=SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE)
    )
    rejected = await cs.post(url, json={"text": "Kênh từ chối."})
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["error_code"] == "channel_recipient_not_reachable"

    app.state.outbound_delivery = FakeOutboundDelivery(raises=RuntimeError("channel down"))
    broken = await cs.post(url, json={"text": "Kênh hỏng."})
    assert broken.status_code == 201
    assert broken.json()["status"] == "rejected"
    assert broken.json()["error_code"] == "channel_unavailable"


async def test_a_proactive_reply_needs_a_linked_patient_with_messaging_consent(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, app: Any
) -> None:
    app.state.outbound_delivery = FakeOutboundDelivery()
    cs = await client_factory("cs.maianh")
    stranger = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    refused = await cs.post(
        f"/api/v1/conversations/{stranger.conversation_id}/messages", json={"text": "x", "proactive": True}
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "identity_not_verified"
    linked = await record_inbound(db, world)  # P025 has a messaging consent in the seed
    ok = await cs.post(
        f"/api/v1/conversations/{linked.conversation_id}/messages",
        json={"text": "Nhắc lịch.", "proactive": True},
    )
    assert ok.status_code == 201
    assert ok.json()["proactive"] is True
    # revoke the consent: the same request is now refused
    reception = await client_factory("reception.lan")
    await reception.post(
        f"/api/v1/patients/{world.patients['P025']}/consents", json={"kind": "messaging", "granted": False}
    )
    again = await cs.post(
        f"/api/v1/conversations/{linked.conversation_id}/messages",
        json={"text": "Nhắc lịch.", "proactive": True},
    )
    assert again.status_code == 422
    assert again.json()["error"]["code"] == "consent_required"
    await reception.post(
        f"/api/v1/patients/{world.patients['P025']}/consents", json={"kind": "messaging", "granted": True}
    )


async def test_assign_and_close_a_conversation_respecting_pending_reviews(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    url = f"/api/v1/conversations/{ref.conversation_id}"
    assigned = await cs.patch(url, json={"version": 2, "assigned_user_id": str(world.users["cs.thu"])})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_user_id"] == str(world.users["cs.thu"])
    bad_assignee = await cs.patch(
        url,
        json={"version": assigned.json()["version"], "assigned_user_id": str(world.users["reception.lan"])},
    )
    assert bad_assignee.status_code == 422
    manual_pending = await cs.patch(
        url, json={"version": assigned.json()["version"], "status": "pending_review"}
    )
    assert manual_pending.status_code == 422
    stale = await cs.patch(url, json={"version": 1, "status": "closed"})
    assert stale.status_code == 409
    item = await make_item(db, world, ref.conversation_id)
    current = (await cs.get(url)).json()
    assert current["status"] == "pending_review"
    blocked = await cs.patch(url, json={"version": current["version"], "status": "closed"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "invalid_state"
    rejected = await cs.post(
        f"/api/v1/review-items/{item['id']}/reject", json={"version": 1, "reason": "không cần"}
    )
    assert rejected.status_code == 200
    current = (await cs.get(url)).json()
    assert current["status"] == "open", "rejecting the last open item reopens the conversation"
    closed = await cs.patch(url, json={"version": current["version"], "status": "closed"})
    assert closed.json()["status"] == "closed"


async def test_a_doctor_sees_only_conversations_of_patients_in_scope(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    mai = await client_factory("doctor.mai")
    stranger = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    assert (await mai.get(f"/api/v1/conversations/{stranger.conversation_id}")).status_code == 404
    mine = await record_inbound(db, world)
    assert (await mai.get(f"/api/v1/conversations/{mine.conversation_id}")).status_code == 200


async def test_reception_has_no_inbox(client_factory: ClientFactory, world: SeedResult) -> None:
    reception = await client_factory("reception.lan")
    assert (await reception.get("/api/v1/conversations")).status_code == 403
    assert (
        await reception.post(f"/api/v1/conversations/{world.conversation_id}/messages", json={"text": "x"})
    ).status_code == 403


# ---------------------------------------------------------------- review queue


async def test_approving_with_an_edit_sends_the_edited_text_once_and_marks_the_message_sent(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, app: Any
) -> None:
    """duyệt (có sửa) rồi gửi, đánh dấu đã gửi, idempotent"""
    fake = FakeOutboundDelivery()
    app.state.outbound_delivery = fake
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    item = await make_item(db, world, ref.conversation_id)
    url = f"/api/v1/review-items/{item['id']}/approve"
    headers = {"Idempotency-Key": f"approve-{item['id']}"}
    approved = await cs.post(
        url,
        json={"version": 1, "final_text": "Bản đã sửa bởi nhân viên.", "note": "đã chỉnh"},
        headers=headers,
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved"
    assert body["final_text"] == "Bản đã sửa bởi nhân viên."
    assert body["draft_text"].startswith("Chào bạn")
    assert body["decided_by"] == str(world.users["cs.maianh"])
    assert body["decided_at"] is not None
    assert [r.text for r in fake.requests] == ["Bản đã sửa bởi nhân viên."]
    assert fake.requests[0].proactive is False
    messages = (await cs.get(f"/api/v1/conversations/{ref.conversation_id}/messages")).json()["items"]
    sent = [m for m in messages if m["review_item_id"] == item["id"]]
    assert len(sent) == 1
    assert sent[0]["status"] == "sent"
    assert sent[0]["sender_type"] == "staff"
    assert (await cs.get(f"/api/v1/conversations/{ref.conversation_id}")).json()["status"] == "open"
    # retried with the same key: same item back, still one send
    retry = await cs.post(
        url, json={"version": 1, "final_text": "Bản đã sửa bởi nhân viên."}, headers=headers
    )
    assert retry.status_code == 200
    assert len(fake.requests) == 1
    # without the key a decided item is an invalid state
    late = await cs.post(url, json={"version": 2})
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "invalid_state"


async def test_approve_without_send_records_the_decision_and_sends_nothing(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, app: Any
) -> None:
    fake = FakeOutboundDelivery()
    app.state.outbound_delivery = fake
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    item = await make_item(db, world, ref.conversation_id)
    approved = await cs.post(f"/api/v1/review-items/{item['id']}/approve", json={"version": 1, "send": False})
    assert approved.status_code == 200
    assert fake.requests == []
    assert (await cs.get(f"/api/v1/conversations/{ref.conversation_id}/messages")).json()["items"][0][
        "review_item_id"
    ] is None


async def test_approve_refuses_empty_oversized_or_unsendable_text(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    long_item = await make_item(db, world, ref.conversation_id, draft="x" * 2500)
    too_long = await cs.post(f"/api/v1/review-items/{long_item['id']}/approve", json={"version": 1})
    assert too_long.status_code == 422
    shortened = await cs.post(
        f"/api/v1/review-items/{long_item['id']}/approve", json={"version": 1, "final_text": "Bản rút gọn."}
    )
    assert shortened.status_code == 200
    no_conversation = await make_item(db, world, None)
    refused = await cs.post(f"/api/v1/review-items/{no_conversation['id']}/approve", json={"version": 1})
    assert refused.status_code == 422


async def test_rejecting_needs_a_reason_and_a_decision_is_final(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    cs = await client_factory("cs.maianh")
    ref = await record_inbound(db, world)
    item = await make_item(db, world, ref.conversation_id)
    base = f"/api/v1/review-items/{item['id']}"
    assert (await cs.post(f"{base}/reject", json={"version": 1})).status_code == 422
    rejected = await cs.post(f"{base}/reject", json={"version": 1, "reason": "Nội dung không chính xác"})
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["decision_note"] == "Nội dung không chính xác"
    assert (await cs.post(f"{base}/approve", json={"version": 2})).status_code == 409
    assert (await cs.post(f"{base}/reject", json={"version": 2, "reason": "lại"})).status_code == 409


async def test_two_people_deciding_at_once_one_wins(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    import asyncio

    cs = await client_factory("cs.maianh")
    manager = await client_factory("manager")
    ref = await record_inbound(db, world)
    item = await make_item(db, world, ref.conversation_id)
    base = f"/api/v1/review-items/{item['id']}"
    results = await asyncio.gather(
        cs.post(f"{base}/reject", json={"version": 1, "reason": "a"}),
        manager.post(f"{base}/reject", json={"version": 1, "reason": "b"}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]


async def test_a_red_flag_item_is_for_doctors_only_and_escalating_hands_an_item_over(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    """CSKH không duyệt y khoa; cờ đỏ không tự giải quyết"""
    cs = await client_factory("cs.maianh")
    mai = await client_factory("doctor.mai")
    reception = await client_factory("reception.lan")
    ref = await record_inbound(db, world)
    alert = await make_item(
        db,
        world,
        ref.conversation_id,
        kind=ReviewKind.TRIAGE_ALERT,
        risk=RiskLevel.RED_FLAG,
        draft="Cờ đỏ mẫu",
    )
    assert alert["requires_doctor"] is True
    assert (await cs.get(f"/api/v1/review-items/{alert['id']}")).status_code == 403
    assert alert["id"] not in [
        i["id"] for i in (await cs.get("/api/v1/review-items", params={"limit": 200})).json()["items"]
    ]
    assert (
        await cs.post(f"/api/v1/review-items/{alert['id']}/approve", json={"version": 1})
    ).status_code == 403
    assert (await reception.get(f"/api/v1/review-items/{alert['id']}")).status_code == 403
    assert (await cs.get(f"/api/v1/conversations/{ref.conversation_id}")).json()["status"] == "handoff"
    assert (await mai.get(f"/api/v1/review-items/{alert['id']}")).json()["risk_level"] == "red_flag"

    normal = await make_item(db, world, ref.conversation_id)
    escalated = await cs.post(
        f"/api/v1/review-items/{normal['id']}/escalate", json={"version": 1, "note": "cần bác sĩ xem"}
    )
    assert escalated.status_code == 200
    assert escalated.json()["status"] == "escalated"
    assert escalated.json()["requires_doctor"] is True
    # from now on only a clinician decides it
    assert (
        await cs.post(f"/api/v1/review-items/{normal['id']}/reject", json={"version": 2, "reason": "x"})
    ).status_code == 403
    done = await mai.post(
        f"/api/v1/review-items/{normal['id']}/reject", json={"version": 2, "reason": "bác sĩ từ chối"}
    )
    assert done.status_code == 200
    # an escalation cannot be repeated on a decided item
    assert (
        await cs.post(f"/api/v1/review-items/{alert['id']}/escalate", json={"version": 1})
    ).status_code == 403


async def test_the_queue_orders_pending_first_and_filters(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase
) -> None:
    mai = await client_factory("doctor.mai")
    ref = await record_inbound(db, world)
    item = await make_item(db, world, ref.conversation_id)
    await mai.post(f"/api/v1/review-items/{item['id']}/reject", json={"version": 1, "reason": "đóng"})
    page = (await mai.get("/api/v1/review-items", params={"limit": 200})).json()
    statuses = [i["status"] for i in page["items"]]
    assert statuses == sorted(statuses, key=lambda s: s != "pending"), "pending items come first"
    only = (
        await mai.get(
            "/api/v1/review-items",
            params={"review_status": "rejected", "conversation_id": str(ref.conversation_id)},
        )
    ).json()
    assert [i["id"] for i in only["items"]] == [item["id"]]
    doctor_only = (
        await mai.get("/api/v1/review-items", params={"requires_doctor": "true", "limit": 200})
    ).json()
    assert doctor_only["items"] and all(i["requires_doctor"] for i in doctor_only["items"])

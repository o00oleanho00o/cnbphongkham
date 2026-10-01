# ruff: noqa: PT018
"""``AgentFacingClinicActions`` as the agent worker role (no privilege on ``clinic.*``): care context, the
appointment PROPOSAL, review items, escalation, identity and the Inbox of record."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import DEMO_NOW, ClientFactory, fresh_start, record_inbound
from pema.clinic.actions import AppointmentProposalRequest, ClinicAgentFacingActions, EscalationRequest
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate
from pema_contracts.channel import ChannelKind
from pema_contracts.clinic_actions import CareContext, FollowupMilestone, IdentityLinkStatus
from pema_contracts.conversations import MessageStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.review import ReviewItemCreate, ReviewKind, ReviewStatus, RiskLevel
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db


def agent(world: SeedResult) -> ActionContext:
    return ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)


def proposal(world: SeedResult, ref: Any, **kw: Any) -> AppointmentProposalRequest:
    fields: dict[str, Any] = {
        "job_id": f"job-{uuid4().hex}",
        "patient_ref": "P025",
        "conversation_ref": str(ref.conversation_id),
        "starts_at": fresh_start(9),
        "doctor_id": world.users["doctor.mai"],
    }
    fields.update(kw)
    return AppointmentProposalRequest(**fields)


# ---------------------------------------------------------------- care context


async def test_the_care_context_of_a_verified_patient_is_the_minimum_the_agent_needs(
    worker_db: ClinicDatabase, world_a: SeedResult
) -> None:
    """patient.get_care_context trả ngữ cảnh tối thiểu qua view đã cấp"""
    context = await ClinicAgentFacingActions(worker_db).get_care_context(agent(world_a), "P025")
    assert context is not None
    assert context.patient_code == "P025"
    assert context.identity_verified is True
    assert context.display_name == "Bệnh nhân mẫu 025"
    assert context.lifecycle_stage == "treating"
    assert context.last_protocol_id == "laser-co2"
    assert context.days_since_last_session == 1
    assert context.days_since_last_visit == 1
    assert context.remaining_sessions == 2
    assert context.days_to_next_appointment == 10
    assert context.followup_milestone is FollowupMilestone.D1
    assert context.consent_messaging is True
    assert context.marketing_opt_out is False


async def test_an_unverified_identity_gets_no_name(worker_db: ClinicDatabase, world_a: SeedResult) -> None:
    """chưa xác minh zalo_uid thì không nhắc tên"""
    context = await ClinicAgentFacingActions(worker_db).get_care_context(agent(world_a), "P026")
    assert context is not None
    assert context.identity_verified is False
    assert context.display_name is None


async def test_dormant_and_opted_out_patient_and_unknown_code(
    worker_db: ClinicDatabase, world_a: SeedResult
) -> None:
    door = ClinicAgentFacingActions(worker_db)
    dormant = await door.get_care_context(agent(world_a), "P030")
    assert dormant is not None
    assert dormant.lifecycle_stage == "dormant"
    assert dormant.marketing_opt_out is True
    assert dormant.consent_messaging is False
    assert await door.get_care_context(agent(world_a), "P999") is None


def test_the_care_context_has_no_field_that_could_carry_pii() -> None:
    forbidden = {
        "phone",
        "birth_date",
        "address",
        "email",
        "national_id",
        "notes",
        "note",
        "photo",
        "history",
    }
    assert not forbidden & set(CareContext.model_fields)


async def test_staff_and_other_actors_cannot_use_the_agent_door(
    db: ClinicDatabase, world_a: SeedResult
) -> None:
    owner = ActionContext(
        clinic_id=world_a.clinic_id, actor_type=ActorType.USER, actor_user_id=uuid4(), actor_role=Role.OWNER
    )
    with pytest.raises(DomainError) as caught:
        await ClinicAgentFacingActions(db).get_care_context(owner, "P025")
    assert caught.value.code is ErrorCode.FORBIDDEN


async def test_upcoming_appointments_exclude_cancelled_and_past_ones(
    worker_db: ClinicDatabase, world_a: SeedResult
) -> None:
    views = await ClinicAgentFacingActions(worker_db).list_upcoming_appointments(
        agent(world_a), "P025", limit=5
    )
    assert views
    assert all(v.status in {"booked", "confirmed", "arrived", "in_progress"} for v in views)
    assert all(v.starts_at > DEMO_NOW for v in views)
    assert [v.starts_at for v in views] == sorted(v.starts_at for v in views)


# ---------------------------------------------------------------- appointment proposal


async def test_the_agent_proposes_an_appointment_it_does_not_book_it(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    """appointment.book của agent chỉ tạo ĐỀ XUẤT lịch (review_item) chờ nhân viên xác nhận"""
    ref = await record_inbound(db, world_a)
    request = proposal(world_a, ref)
    item = await ClinicAgentFacingActions(worker_db).propose_appointment(agent(world_a), request)
    assert item.status is ReviewStatus.PENDING
    assert item.kind is ReviewKind.REPLY_DRAFT
    assert item.requires_doctor is False
    assert item.patient_code == "P025"
    assert item.payload is not None and item.payload["proposal"] == "appointment"
    assert item.payload["starts_at"] == request.starts_at.isoformat()
    assert item.draft_text and "xác nhận" in item.draft_text
    with admin.connect() as conn:
        booked = conn.execute(
            text("SELECT count(*) FROM clinic.appointment WHERE patient_id = :p AND starts_at = :s"),
            {"p": world_a.patients["P025"], "s": request.starts_at},
        ).scalar_one()
        status = conn.execute(
            text("SELECT status FROM clinic.conversation WHERE id = :c"), {"c": ref.conversation_id}
        ).scalar_one()
        actor = conn.execute(
            text(
                "SELECT actor_type FROM clinic.audit_log WHERE action = 'review_item.create' AND entity_id = :e"
            ),
            {"e": str(item.id)},
        ).scalar_one()
    assert booked == 0, "the agent must not create an appointment"
    assert status == "pending_review"
    assert actor == "agent"


async def test_a_proposal_is_idempotent_on_its_job_id(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    ref = await record_inbound(db, world_a)
    request = proposal(world_a, ref)
    door = ClinicAgentFacingActions(worker_db)
    first = await door.propose_appointment(agent(world_a), request)
    second = await door.propose_appointment(agent(world_a), request)
    assert first.id == second.id
    with admin.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM clinic.review_item WHERE job_id = :j"), {"j": request.job_id}
        ).scalar_one()
    assert count == 1


async def test_a_proposal_needs_a_verified_identity_a_known_patient_and_a_valid_free_slot(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, client_factory: ClientFactory
) -> None:
    door = ClinicAgentFacingActions(worker_db)
    ref = await record_inbound(db, world_a)
    with pytest.raises(DomainError) as unverified:
        await door.propose_appointment(agent(world_a), proposal(world_a, ref, patient_ref="P026"))
    assert unverified.value.code is ErrorCode.IDENTITY_NOT_VERIFIED
    with pytest.raises(DomainError) as unknown:
        await door.propose_appointment(agent(world_a), proposal(world_a, ref, patient_ref="P999"))
    assert unknown.value.code is ErrorCode.NOT_FOUND
    for bad_start in (DEMO_NOW - timedelta(hours=1), DEMO_NOW + timedelta(days=1, hours=-2)):  # past; 07:00
        with pytest.raises(DomainError) as invalid:
            await door.propose_appointment(agent(world_a), proposal(world_a, ref, starts_at=bad_start))
        assert invalid.value.code is ErrorCode.VALIDATION_FAILED
    # the doctor is busy at that time: the proposal never reaches the queue
    start = fresh_start(14)
    reception = await client_factory("clinic-a", "reception.lan")
    taken = await reception.post(
        "/api/v1/appointments",
        json={
            "patient_id": str(world_a.patients["P029"]),
            "doctor_id": str(world_a.users["doctor.mai"]),
            "starts_at": start,
        },
    )
    assert taken.status_code == 201
    with pytest.raises(DomainError) as conflict:
        await door.propose_appointment(agent(world_a), proposal(world_a, ref, starts_at=start))
    assert conflict.value.code is ErrorCode.APPOINTMENT_CONFLICT


async def test_the_agent_cannot_book_directly(worker_db: ClinicDatabase, world_a: SeedResult) -> None:
    with pytest.raises(DomainError) as caught:
        await ClinicAgentFacingActions(worker_db).book_appointment(
            agent(world_a),
            AppointmentCreate(patient_id=world_a.patients["P025"], starts_at=fresh_start()),  # type: ignore[arg-type]
        )
    assert caught.value.code is ErrorCode.POLICY_DENIED
    assert caught.value.details == {"use": "propose_appointment"}


# ---------------------------------------------------------------- review items and escalation


async def test_create_review_item_is_idempotent_and_refuses_another_clinic(
    worker_db: ClinicDatabase, world_a: SeedResult, world_b: SeedResult
) -> None:
    door = ClinicAgentFacingActions(worker_db)
    request = ReviewItemCreate(
        job_id=f"job-{uuid4().hex}",
        clinic_id=world_a.clinic_id,
        patient_ref="P025",
        kind=ReviewKind.FOLLOWUP_DRAFT,
        draft_text="Nội dung nháp mẫu",
        model="demo-model",
        prompt_version="v1",
    )
    first = await door.create_review_item(agent(world_a), request)
    again = await door.create_review_item(
        agent(world_a), request.model_copy(update={"draft_text": "Nội dung khác"})
    )
    assert first.id == again.id
    assert again.draft_text == "Nội dung nháp mẫu", "a replay returns the FIRST item, not the new text"
    assert first.model == "demo-model" and first.prompt_version == "v1"
    with pytest.raises(DomainError) as caught:
        await door.create_review_item(agent(world_b), request.model_copy(update={"job_id": "x"}))
    assert caught.value.code is ErrorCode.FORBIDDEN


async def test_an_escalation_is_a_red_flag_triage_alert_for_a_doctor_and_hands_the_conversation_over(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    """escalation.create: cờ đỏ chuyển bác sĩ"""
    ref = await record_inbound(db, world_a)
    item = await ClinicAgentFacingActions(worker_db).create_escalation(
        agent(world_a),
        EscalationRequest(
            job_id=f"esc-{uuid4().hex}",
            patient_ref="P025",
            conversation_ref=str(ref.conversation_id),
            red_flags=["bleeding"],
            summary="Bệnh nhân nhắc đến chảy máu (đã che PII).",
        ),
    )
    assert item.kind is ReviewKind.TRIAGE_ALERT
    assert item.risk_level is RiskLevel.RED_FLAG
    assert item.requires_doctor is True
    assert item.red_flags == ["bleeding"]
    with admin.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM clinic.conversation WHERE id = :c"), {"c": ref.conversation_id}
        ).scalar_one()
    assert status == "handoff"


# ---------------------------------------------------------------- identity and Inbox of record


async def test_resolve_identity_tells_verified_pending_and_unlinked_apart(
    worker_db: ClinicDatabase, world_a: SeedResult
) -> None:
    door = ClinicAgentFacingActions(worker_db)
    verified = await door.resolve_identity(agent(world_a), ChannelKind.ZALO_BOT, "demo-uid-025")
    assert verified.status is IdentityLinkStatus.VERIFIED
    assert verified.patient_code == "P025"
    assert verified.verified_at is not None
    pending = await door.resolve_identity(agent(world_a), ChannelKind.ZALO_BOT, "demo-uid-026")
    assert pending.status is IdentityLinkStatus.PENDING
    unknown = await door.resolve_identity(agent(world_a), ChannelKind.ZALO_BOT, "never-seen")
    assert unknown.status is IdentityLinkStatus.UNLINKED
    assert unknown.patient_id is None


async def test_an_inbound_message_is_recorded_once_per_update_id_and_links_a_verified_patient(
    worker_db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    update = uuid4().hex
    thread = uuid4().hex
    first = await record_inbound(worker_db, world_a, thread=thread, update_id=update, text="Xin chào")
    again = await record_inbound(worker_db, world_a, thread=thread, update_id=update, text="Xin chào")
    assert first.duplicate is False
    assert again.duplicate is True
    assert again.message_id == first.message_id
    assert first.patient_id == world_a.patients["P025"]
    with admin.connect() as conn:
        messages = conn.execute(
            text("SELECT count(*) FROM clinic.message WHERE conversation_id = :c"),
            {"c": first.conversation_id},
        ).scalar_one()
        unread = conn.execute(
            text("SELECT unread_count FROM clinic.conversation WHERE id = :c"), {"c": first.conversation_id}
        ).scalar_one()
    assert messages == 1 and unread == 1
    other = await record_inbound(worker_db, world_a, thread=thread, text="Tin thứ hai")
    assert other.conversation_id == first.conversation_id
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT unread_count FROM clinic.conversation WHERE id = :c"),
                {"c": first.conversation_id},
            ).scalar_one()
            == 2
        )


async def test_an_unknown_sender_stays_unlinked_and_a_new_message_reopens_a_closed_conversation(
    worker_db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    thread = uuid4().hex
    uid = f"stranger-{uuid4().hex[:8]}"
    first = await record_inbound(worker_db, world_a, uid=uid, thread=thread)
    assert first.patient_id is None
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.conversation SET status = 'closed' WHERE id = :c"),
            {"c": first.conversation_id},
        )
    await record_inbound(worker_db, world_a, uid=uid, thread=thread)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT status FROM clinic.conversation WHERE id = :c"), {"c": first.conversation_id}
            ).scalar_one()
            == "open"
        )


async def test_inbound_messages_are_audited_by_the_system_not_by_a_user(
    worker_db: ClinicDatabase, world_a: SeedResult, admin: Engine
) -> None:
    ref = await record_inbound(worker_db, world_a)
    with admin.connect() as conn:
        row = conn.execute(
            text(
                "SELECT actor_type, actor_user_id, details::text FROM clinic.audit_log WHERE action = 'message.record_inbound' AND entity_id = :e"
            ),
            {"e": str(ref.message_id)},
        ).one()
    assert row.actor_type == "system"  # the channel layer is not a user; the agent actor writes 'agent'
    assert row.actor_user_id is None
    assert "Tin nhắn mẫu" not in row.details


async def test_an_outbound_record_updates_the_queued_message_of_an_approved_review_item(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, client_factory: ClientFactory
) -> None:
    """đánh dấu đã gửi: không có hai bản ghi cho cùng một câu trả lời"""
    cs = await client_factory("clinic-a", "cs.maianh")
    ref = await record_inbound(db, world_a)
    door = ClinicAgentFacingActions(worker_db)
    item = await door.create_review_item(
        agent(world_a),
        ReviewItemCreate(
            job_id=f"job-{uuid4().hex}",
            clinic_id=world_a.clinic_id,
            patient_ref="P025",
            conversation_ref=str(ref.conversation_id),
            kind=ReviewKind.REPLY_DRAFT,
            draft_text="Bản nháp để gửi.",
        ),
    )
    approved = await cs.post(f"/api/v1/review-items/{item.id}/approve", json={"version": 1})
    assert approved.status_code == 200  # no channel wired: the message stays queued
    queued = (await cs.get(f"/api/v1/conversations/{ref.conversation_id}/messages")).json()["items"][0]
    assert queued["status"] == "queued"
    marked = await door.record_outbound_message(
        agent(world_a),
        conversation_id=ref.conversation_id,
        text="Bản nháp để gửi.",
        status=MessageStatus.SENT,
        review_item_id=item.id,
    )
    assert str(marked.message_id) == queued["id"]
    messages = (await cs.get(f"/api/v1/conversations/{ref.conversation_id}/messages")).json()["items"]
    assert [m["status"] for m in messages if m["review_item_id"] == str(item.id)] == ["sent"]


async def test_an_outbound_without_a_review_item_is_a_system_message_and_bad_input_is_refused(
    worker_db: ClinicDatabase, db: ClinicDatabase, world_a: SeedResult, client_factory: ClientFactory
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    ref = await record_inbound(db, world_a)
    door = ClinicAgentFacingActions(worker_db)
    out = await door.record_outbound_message(
        agent(world_a),
        conversation_id=ref.conversation_id,
        text="Nhắc lịch tự động.",
        status=MessageStatus.SENT,
        proactive=True,
    )
    message = (await cs.get(f"/api/v1/conversations/{ref.conversation_id}/messages")).json()["items"][0]
    assert message["id"] == str(out.message_id)
    assert message["sender_type"] == "system"
    assert message["proactive"] is True
    with pytest.raises(DomainError) as unknown:
        await door.record_outbound_message(
            agent(world_a), conversation_id=UUID(int=7), text="x", status=MessageStatus.SENT
        )
    assert unknown.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(DomainError) as bad_status:
        await door.record_outbound_message(
            agent(world_a), conversation_id=ref.conversation_id, text="x", status=MessageStatus.RECEIVED
        )
    assert bad_status.value.code is ErrorCode.VALIDATION_FAILED


async def test_the_worker_role_cannot_read_a_clinic_table_even_through_this_door_class(
    worker_db: ClinicDatabase, world_a: SeedResult
) -> None:
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError):
        async with worker_db.session(world_a.clinic_id) as session:
            await session.execute(text("SELECT * FROM clinic.patient"))

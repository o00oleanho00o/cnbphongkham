"""ORM rows to wire DTOs. New module; no logic beyond conversion (string columns become enums)."""

from __future__ import annotations

from uuid import UUID

from pema.clinic.models import (
    Appointment,
    AuditLog,
    Consent,
    CrmActivity,
    CrmTask,
    Patient,
)
from pema_contracts.admin import AuditLogOut
from pema_contracts.appointments import AppointmentOut, AppointmentStatus
from pema_contracts.crm import (
    CrmActivityOut,
    CrmChannel,
    CrmOutcome,
    CrmTaskOut,
    RuleKey,
    TaskPriority,
    TaskStatus,
)
from pema_contracts.patients import ConsentKind, ConsentOut, Gender, PatientOut
from pema_contracts.roles import ActorType, Role


def patient_out(row: Patient, doctor_name: str | None = None, cs_owner_name: str | None = None) -> PatientOut:
    return PatientOut(
        id=row.id,
        code=row.code,
        full_name=row.full_name,
        phone=row.phone,
        birth_date=row.birth_date,
        gender=Gender(row.gender),
        doctor_id=row.doctor_id,
        doctor_name=doctor_name,
        cs_owner_id=row.cs_owner_id,
        cs_owner_name=cs_owner_name,
        marketing_opt_out=row.marketing_opt_out,
        first_contact_at=row.first_contact_at,
        source=row.source,
        version=row.version,
    )


def appointment_out(row: Appointment, patient_code: str) -> AppointmentOut:
    return AppointmentOut(
        id=row.id,
        patient_id=row.patient_id,
        patient_code=patient_code,
        doctor_id=row.doctor_id,
        room_id=row.room_id,
        starts_at=row.starts_at,
        duration_min=row.duration_min,
        status=AppointmentStatus(row.status),
        note=row.note,
        cancel_reason=row.cancel_reason,
        cancelled_at=row.cancelled_at,
        missed_at=row.missed_at,
        created_by=row.created_by,
        version=row.version,
    )


def task_out(row: CrmTask, patient_code: str, owner_name: str | None) -> CrmTaskOut:
    return CrmTaskOut(
        id=row.id,
        patient_id=row.patient_id,
        patient_code=patient_code,
        rule_key=RuleKey(row.rule_key),
        task_key=row.task_key,
        reason=row.reason,
        priority=TaskPriority(row.priority),
        status=TaskStatus(row.status),
        owner_user_id=row.owner_user_id,
        owner_name=owner_name,
        due_at=row.due_at,
        created_at=row.created_at,
        suggested_action=row.suggested_action,
        source_event_id=row.source_event_id,
        related_appointment_id=row.related_appointment_id,
        resolution=row.resolution,
        resolved_at=row.resolved_at,
        version=row.version,
    )


def activity_out(row: CrmActivity, actor_name: str | None) -> CrmActivityOut:
    return CrmActivityOut(
        id=row.id,
        patient_id=row.patient_id,
        task_id=row.task_id,
        kind=row.kind,
        channel=CrmChannel(row.channel),
        outcome=CrmOutcome(row.outcome) if row.outcome else None,
        note=row.note,
        actor_user_id=row.actor_user_id,
        actor_name=actor_name,
        occurred_at=row.occurred_at,
        next_action_at=row.next_action_at,
        related_appointment_id=row.related_appointment_id,
    )


def consent_out(row: Consent) -> ConsentOut:
    return ConsentOut(
        id=row.id,
        kind=ConsentKind(row.kind),
        granted=row.granted,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
        source=row.source,
    )


def audit_out(row: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=row.id,
        occurred_at=row.occurred_at,
        actor_type=ActorType(row.actor_type),
        actor_user_id=row.actor_user_id,
        actor_role=Role(row.actor_role) if row.actor_role else None,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        request_id=row.request_id,
        details=row.details,
    )


def uuid_or_none(value: str | None) -> UUID | None:
    return UUID(value) if value else None

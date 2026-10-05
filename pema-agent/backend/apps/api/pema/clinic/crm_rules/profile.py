# ported from: prototype/shared/crm-automation.js (upcoming, profile, refresh)
"""The CRM read model of a patient and the protocol recommendation step.

Pure functions of a ``PatientSnapshot`` and ``today`` (the clinic-local day of ``now``).

* ``upcoming``: appointments that are active, not completed and on or after today, soonest first. A cancelled
  or missed appointment is NOT a booking and never counts as the patient having come (docs 20_CRM01).
* ``compute_profile`` is ``profile(p)``: the next real appointment wins over the saved recommendation; a
  cancelled booking therefore falls back to the recommendation. ``overdue_days = max(0, today - expected)``.
  A patient is at risk when there is no new booking and (overdue by more than 7 days, or sessions remain and
  the last visit was more than 45 days ago). A booked patient is still not "reactivated": only the real
  check-in sets ``reactivated_at``.
* ``refresh_patient`` is the patient part of ``refresh()``: when the latest session of protocol Laser CO2 has
  not yet produced a recommendation, ``recommendation_at`` becomes that session + 30 days (source
  ``service_protocol``). The session id is remembered so a doctor's later edit of the date is never
  overwritten; the original kept it in ``p.crm.lastProtocolSession``.
  The protocol and its ``followup_days`` are data now (``ProtocolConfig``): any active protocol that has a
  ``followup_days`` recommends it, and with no configuration Laser CO2 keeps its 30 days.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date

from pema.clinic.crm_rules.dates import add_days, days_between
from pema.clinic.crm_rules.protocols import ProtocolConfig, protocol_for
from pema.clinic.crm_rules.records import (
    AppointmentSnapshot,
    AppointmentStatus,
    LifecycleStage,
    PatientCrmUpdate,
    PatientSnapshot,
    ProfileView,
    RiskLevel,
    SessionSnapshot,
)
from pema_contracts.crm import CrmProfile

APPOINTMENT_VISIT_REASON = "Lịch hẹn đã xác nhận với phòng khám"
SERVICE_PROTOCOL_SOURCE = "service_protocol"
APPOINTMENT_SOURCE = "appointment"
DORMANT_AFTER_DAYS = 90
RISK_OVERDUE_DAYS = 7
RISK_IDLE_DAYS = 45


def upcoming(patient: PatientSnapshot, today: date) -> list[AppointmentSnapshot]:
    """``upcoming(p)``: active, not completed, day >= today, ordered by start."""
    rows = [
        a
        for a in patient.appointments
        if a.active and a.status is not AppointmentStatus.COMPLETED and a.day >= today
    ]
    return sorted(rows, key=lambda a: a.starts_at)


def latest_session(patient: PatientSnapshot) -> SessionSnapshot | None:
    """Latest session by day; on a tie the first one listed (the JavaScript sort is stable)."""
    if not patient.sessions:
        return None
    return sorted(patient.sessions, key=lambda s: s.day, reverse=True)[0]


def compute_profile(patient: PatientSnapshot, today: date) -> ProfileView:
    """``profile(p)``."""
    next_appointment = next(iter(upcoming(patient, today)), None)
    expected = next_appointment.day if next_appointment is not None else patient.recommendation_at
    age = days_between(patient.last_visit, today) if patient.last_visit is not None else 0
    remaining = max(0, patient.total_sessions - patient.completed_sessions)
    overdue = max(0, days_between(expected, today)) if expected is not None else 0
    if patient.reactivated_at is not None:
        stage = LifecycleStage.REACTIVATED
    elif not patient.sessions:
        stage = LifecycleStage.NEW
    elif age >= DORMANT_AFTER_DAYS:
        stage = LifecycleStage.DORMANT
    elif remaining > 0:
        stage = LifecycleStage.TREATING
    else:
        stage = LifecycleStage.RETURNING
    at_risk = next_appointment is None and (
        overdue > RISK_OVERDUE_DAYS or (remaining > 0 and age > RISK_IDLE_DAYS)
    )
    return ProfileView(
        last_visit_at=patient.last_visit,
        expected_next_visit_at=expected,
        expected_visit_source=APPOINTMENT_SOURCE
        if next_appointment is not None
        else patient.expected_visit_source,
        expected_visit_reason=(
            APPOINTMENT_VISIT_REASON if next_appointment is not None else patient.expected_visit_reason
        ),
        overdue_days=overdue,
        lifecycle_stage=stage,
        remaining=remaining,
        risk_level=RiskLevel.HIGH if at_risk else RiskLevel.NORMAL,
        age=age,
        marketing_opt_out=patient.marketing_opt_out,
    )


def to_profile_dto(view: ProfileView) -> CrmProfile:
    """The wire shape of ``pema_contracts.crm.CrmProfile`` (Patient 360 of package B1 uses it)."""
    return CrmProfile(
        lifecycle_stage=view.lifecycle_stage.value,
        last_visit_at=view.last_visit_at,
        expected_next_visit_at=view.expected_next_visit_at,
        expected_visit_source=view.expected_visit_source,
        overdue_days=view.overdue_days,
        remaining_sessions=view.remaining,
        risk_level=view.risk_level.value,
        marketing_opt_out=view.marketing_opt_out,
    )


def refresh_patient(
    patient: PatientSnapshot, protocols: Mapping[str, ProtocolConfig] | None = None
) -> tuple[PatientSnapshot, PatientCrmUpdate | None]:
    """The patient part of ``refresh()``: the follow-up recommendation after a new session of a protocol that
    has one (Laser CO2: D+30).

    Returns the patient with the recommendation applied and the update to persist (None when nothing changed).
    """
    latest = latest_session(patient)
    if latest is None:
        return patient, None
    config = protocol_for(protocols, latest.protocol_id)
    if config is None or not config.active or config.followup_days is None:
        return patient, None
    if patient.last_protocol_session_id == latest.id:
        return patient, None
    update = PatientCrmUpdate(
        patient_id=patient.id,
        recommendation_at=add_days(latest.day, config.followup_days),
        expected_visit_source=SERVICE_PROTOCOL_SOURCE,
        expected_visit_reason=f"Đánh giá D+{config.followup_days} sau {config.name}",
        last_protocol_session_id=latest.id,
    )
    refreshed = replace(
        patient,
        recommendation_at=update.recommendation_at,
        expected_visit_source=update.expected_visit_source,
        expected_visit_reason=update.expected_visit_reason,
        last_protocol_session_id=update.last_protocol_session_id,
    )
    return refreshed, update

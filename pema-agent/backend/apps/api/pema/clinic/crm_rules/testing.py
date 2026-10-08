# new module (test support, like ``pema_contracts.testing``)
"""Builders for the tests of the CRM rules (patients, sessions, appointments at a fixed clock)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from pema.clinic.crm_rules.records import (
    AppointmentSnapshot,
    AppointmentStatus,
    PatientSnapshot,
    SessionSnapshot,
)
from pema_contracts.common import VN_TZ

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=VN_TZ)
"""The fixed clock of crm-data.js (``DAY = '2026-09-20'``) at the 09:00 the JavaScript uses for due times."""


def appointment(
    id: str,
    day: date,
    *,
    hour: int = 10,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
    cancelled_at: datetime | None = None,
    missed_at: datetime | None = None,
) -> AppointmentSnapshot:
    return AppointmentSnapshot(
        id=id,
        starts_at=datetime(day.year, day.month, day.day, hour, 0, tzinfo=VN_TZ),
        status=status,
        cancelled_at=cancelled_at,
        missed_at=missed_at,
    )


def make_patient(code: str = "P900", **fields: Any) -> PatientSnapshot:
    """A synthetic patient with sensible defaults; override any field by name."""
    return replace(PatientSnapshot(id=uuid4(), code=code), **fields)


def session(id: str, day: date, protocol_id: str | None = None) -> SessionSnapshot:
    return SessionSnapshot(id=id, day=day, protocol_id=protocol_id)

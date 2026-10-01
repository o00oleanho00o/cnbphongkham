# ported from: prototype/shared/operations-data.js (validate) and prototype/shared/crm-automation.js (profile)
"""Scheduling rules and the CRM profile, pure. The clock is the prototype's demo day 2026-09-20."""

from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pytest

from pema.clinic.domain import appointments as rules
from pema.clinic.domain.profile import ProfileFacts, compute_profile
from pema_contracts.appointments import AppointmentStatus
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=VN_TZ)
DOCTOR = uuid4()
OTHER_DOCTOR = uuid4()
PATIENT = uuid4()
OTHER_PATIENT = uuid4()


def _at(hour: int, minute: int = 0, day: int = 21) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=VN_TZ)


def _slot(patient: object, doctor: object, start: datetime, minutes: int = 30, **kw: object) -> rules.Slot:
    return rules.Slot(patient_id=patient, doctor_id=doctor, starts_at=start, duration_min=minutes, **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------- validate_slot


def test_a_slot_inside_the_shift_is_valid() -> None:
    rules.validate_slot(_at(8), 30, NOW)
    rules.validate_slot(_at(17, 30), 30, NOW)  # ends exactly at 18:00
    rules.validate_slot(_at(13), 45, NOW)  # right after the break


@pytest.mark.parametrize(
    ("start", "minutes"),
    [
        (_at(7, 30), 30),  # before 08:00
        (_at(17, 45), 30),  # ends after 18:00
        (_at(11, 45), 30),  # runs into the 12:00-13:00 break
        (_at(12), 30),  # inside the break
        (_at(12, 30), 60),  # starts in the break
        (_at(23), 120),  # crosses midnight
    ],
)
def test_a_slot_outside_the_shift_or_in_the_break_is_refused(start: datetime, minutes: int) -> None:
    """Ngoài ca bác sĩ hoặc trùng giờ nghỉ 12:00–13:00"""
    with pytest.raises(DomainError) as caught:
        rules.validate_slot(start, minutes, NOW)
    assert caught.value.code is ErrorCode.VALIDATION_FAILED


def test_a_day_before_today_is_refused_but_an_earlier_time_today_is_accepted_for_the_ui() -> None:
    with pytest.raises(DomainError):
        rules.validate_slot(_at(10, day=19), 30, NOW)
    rules.validate_slot(_at(8, day=20), 30, NOW)  # JS only compares the date
    with pytest.raises(DomainError):
        rules.validate_slot(_at(8, day=20), 30, NOW, require_future=True)  # an agent proposal must be ahead


def test_a_naive_datetime_is_refused() -> None:
    with pytest.raises(DomainError):
        rules.validate_slot(datetime(2026, 9, 21, 9, 0), 30, NOW)


# ---------------------------------------------------------------- double booking


def test_same_doctor_overlapping_is_a_doctor_conflict() -> None:
    """Trùng bác sĩ"""
    existing = [_slot(OTHER_PATIENT, DOCTOR, _at(9), 30)]
    conflict = rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9, 15), 30), existing)
    assert conflict is not None
    assert conflict.kind == "doctor"


def test_same_patient_overlapping_is_a_patient_conflict_even_with_another_doctor() -> None:
    """Trùng bệnh nhân"""
    existing = [_slot(PATIENT, OTHER_DOCTOR, _at(9), 30)]
    conflict = rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9, 29), 30), existing)
    assert conflict is not None
    assert conflict.kind == "patient"


def test_back_to_back_slots_do_not_conflict() -> None:
    existing = [_slot(OTHER_PATIENT, DOCTOR, _at(9), 30)]
    assert rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9, 30), 30), existing) is None
    assert rules.find_conflict(_slot(PATIENT, DOCTOR, _at(8, 30), 30), existing) is None


def test_other_doctor_and_other_patient_do_not_conflict() -> None:
    existing = [_slot(OTHER_PATIENT, OTHER_DOCTOR, _at(9), 30)]
    assert rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9), 30), existing) is None


def test_cancelled_and_missed_appointments_free_their_slot() -> None:
    for status in (AppointmentStatus.CANCELLED, AppointmentStatus.MISSED):
        existing = [_slot(PATIENT, DOCTOR, _at(9), 30, status=status)]
        assert rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9), 30), existing) is None


def test_a_reschedule_does_not_conflict_with_itself() -> None:
    mine = uuid4()
    existing = [_slot(PATIENT, DOCTOR, _at(9), 30, appointment_id=mine)]
    assert rules.find_conflict(_slot(PATIENT, DOCTOR, _at(9, 15), 30, appointment_id=mine), existing) is None


def test_an_appointment_without_a_doctor_only_conflicts_on_the_patient() -> None:
    existing = [_slot(OTHER_PATIENT, None, _at(9), 30)]
    assert rules.find_conflict(_slot(PATIENT, None, _at(9), 30), existing) is None


def test_the_conflict_message_names_nobody() -> None:
    conflict = rules.Conflict("doctor", uuid4(), _at(9))
    with pytest.raises(DomainError) as caught:
        rules.raise_for_conflict(conflict)
    assert caught.value.code is ErrorCode.APPOINTMENT_CONFLICT
    assert "09:00" in caught.value.message


# ---------------------------------------------------------------- profile (the CRM01 cases)

TODAY = date(2026, 9, 20)


def _facts(**overrides: object) -> ProfileFacts:
    base: dict[str, object] = {
        "today": TODAY,
        "last_visit": date(2026, 9, 19),
        "has_sessions": True,
        "total_sessions": 1,
        "completed_sessions": 1,
        "next_appointment": None,
        "recommendation_at": None,
        "expected_visit_source": None,
        "reactivated": False,
        "marketing_opt_out": False,
    }
    base.update(overrides)
    return ProfileFacts(**base)  # type: ignore[arg-type]


def test_new_patient_without_a_session_is_new() -> None:
    assert compute_profile(_facts(has_sessions=False, last_visit=None)).lifecycle_stage == "new"


def test_a_visit_yesterday_with_nothing_left_is_returning() -> None:
    profile = compute_profile(_facts())
    assert profile.lifecycle_stage == "returning"
    assert profile.overdue_days == 0
    assert profile.risk_level == "normal"


def test_p027_expected_14_days_ago_is_overdue_and_high_risk() -> None:
    """03 · Quá hạn 14 ngày"""
    profile = compute_profile(
        _facts(
            last_visit=date(2026, 8, 21),
            recommendation_at=date(2026, 9, 6),
            expected_visit_source="doctor_recommendation",
        )
    )
    assert profile.overdue_days == 14
    assert profile.risk_level == "high"
    assert profile.expected_visit_source == "doctor_recommendation"


def test_p029_three_of_six_sessions_and_sixty_days_away_is_treating_and_high_risk() -> None:
    """05 · Còn 3/6 buổi, vắng 60 ngày"""
    profile = compute_profile(_facts(last_visit=date(2026, 7, 22), total_sessions=6, completed_sessions=3))
    assert profile.lifecycle_stage == "treating"
    assert profile.remaining_sessions == 3
    assert profile.risk_level == "high"


@pytest.mark.parametrize(("age_days", "stage"), [(89, "returning"), (90, "dormant"), (180, "dormant")])
def test_dormant_from_ninety_days(age_days: int, stage: str) -> None:
    last = date.fromordinal(TODAY.toordinal() - age_days)
    assert compute_profile(_facts(last_visit=last)).lifecycle_stage == stage


def test_an_upcoming_appointment_wins_over_the_recommendation_and_removes_the_risk() -> None:
    profile = compute_profile(
        _facts(
            last_visit=date(2026, 7, 22),
            total_sessions=6,
            completed_sessions=3,
            next_appointment=date(2026, 9, 30),
            recommendation_at=date(2026, 9, 1),
        )
    )
    assert profile.expected_next_visit_at == date(2026, 9, 30)
    assert profile.expected_visit_source == "appointment"
    assert profile.overdue_days == 0
    assert profile.risk_level == "normal"


def test_reactivated_beats_every_other_stage_and_the_opt_out_flag_is_carried() -> None:
    profile = compute_profile(_facts(reactivated=True, last_visit=date(2026, 1, 1), marketing_opt_out=True))
    assert profile.lifecycle_stage == "reactivated"
    assert profile.marketing_opt_out is True

"""Retention, scope ``clinic``: ``clinic.*`` rows, run as ``be_app`` (the API process).

New tests (no TS source). What is deleted: expired dashboard sessions. What must survive: patients,
appointments, consent, audit.
"""

from __future__ import annotations

import pytest

from pema.retention.pg_testing import RetentionEnv, Seed
from pema.retention.policy import RetentionPolicy, Scope
from pema.retention.runner import RetentionRunner, ScopeReport

pytestmark = pytest.mark.db


def _policy(**days: int) -> RetentionPolicy:
    keep = dict.fromkeys(
        (
            "history_days",
            "memory_days",
            "usage_days",
            "trace_days",
            "media_days",
            "job_run_days",
            "auth_session_days",
        ),
        0,
    )
    return RetentionPolicy(**(keep | days), batch_size=50)


async def _run(env: RetentionEnv, policy: RetentionPolicy, *, dry_run: bool = False) -> ScopeReport:
    runner = RetentionRunner(env.db, policy, scopes=(Scope.CLINIC,))
    return await runner.run_scope(Scope.CLINIC, dry_run=dry_run)


async def test_patients_appointments_consent_and_audit_are_never_touched(
    env: RetentionEnv, seed: Seed
) -> None:
    c = env.clinic_id
    patient = seed.patient(c)
    seed.sql(
        "INSERT INTO clinic.appointment (clinic_id, patient_id, starts_at) "
        "VALUES (:c, :p, now() - interval '3000 days') RETURNING 1",
        c=c,
        p=patient,
    )
    seed.sql(
        "INSERT INTO clinic.consent (clinic_id, patient_id, kind, granted, created_at) "
        "VALUES (:c, :p, 'messaging', true, now() - interval '3000 days') RETURNING 1",
        c=c,
        p=patient,
    )
    seed.audit(c, age=3000)
    report = await _run(env, _policy(auth_session_days=1, history_days=1))
    assert not report.failed
    assert seed.count("clinic.patient", c) == 1
    assert seed.count("clinic.appointment", c) == 1
    assert seed.count("clinic.consent", c) == 1
    assert seed.count("clinic.audit_log", c, "action = 'synthetic.event'") == 1


async def test_expired_dashboard_sessions_go_after_the_grace_period_and_valid_ones_stay(
    env: RetentionEnv, seed: Seed
) -> None:
    c = env.clinic_id
    user = seed.user(c)
    seed.auth_session(c, user, expired_days_ago=5)
    seed.auth_session(c, user, expired_days_ago=0)
    seed.auth_session(c, user, expired_days_ago=-3)
    report = await _run(env, _policy(auth_session_days=1))
    assert report.clinic_id == c
    assert report.counts["auth_sessions"] == 1
    assert seed.count("clinic.auth_session", c) == 2


async def test_zero_days_keeps_sessions_of_any_age(env: RetentionEnv, seed: Seed) -> None:
    c = env.clinic_id
    seed.auth_session(c, seed.user(c), expired_days_ago=2000)
    report = await _run(env, _policy(auth_session_days=0))
    assert "auth_sessions" in report.disabled
    assert seed.count("clinic.auth_session", c) == 1


async def test_dry_run_counts_what_would_go_and_changes_nothing(env: RetentionEnv, seed: Seed) -> None:
    c = env.clinic_id
    seed.auth_session(c, seed.user(c), expired_days_ago=9)
    report = await _run(env, _policy(auth_session_days=1), dry_run=True)
    assert report.dry_run
    assert report.counts == {"auth_sessions": 1}
    assert seed.count("clinic.auth_session", c) == 1
    assert seed.count("clinic.audit_log", c, "action = 'retention.run'") == 0, "a dry run writes no audit row"

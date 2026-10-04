"""Retention, scope ``clinic``: ``clinic.*`` rows, run as ``be_app`` (the API process).

New tests (no TS source). What is deleted: messages of conversations closed long enough, the empty closed
conversations, expired dashboard sessions, spent or expired identity-link codes, old link attempts. What must
survive: open conversations, anything an open review item points at, patients, appointments, consent, audit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from pema.conversation.pg_testing import ClinicEnv
from pema.retention.pg_testing import Seed
from pema.retention.policy import RetentionPolicy, Scope
from pema.retention.runner import RetentionRunner, ScopeReport

pytestmark = pytest.mark.db


def _policy(**days: int) -> RetentionPolicy:
    keep = dict.fromkeys(
        (
            "history_days",
            "memory_days",
            "message_days",
            "usage_days",
            "trace_days",
            "media_days",
            "job_run_days",
            "auth_session_days",
            "link_code_days",
            "link_attempt_days",
        ),
        0,
    )
    return RetentionPolicy(**(keep | days), batch_size=50)


async def _run(env: ClinicEnv, policy: RetentionPolicy, *, dry_run: bool = False) -> ScopeReport:
    runner = RetentionRunner(env.db, policy, scopes=(Scope.CLINIC,))
    return await runner.run_scope(env.clinic_id, Scope.CLINIC, dry_run=dry_run)


async def test_messages_of_a_conversation_closed_long_ago_are_deleted_and_the_empty_conversation_goes(
    env: ClinicEnv, seed: Seed
) -> None:
    c = env.clinic_id
    old_closed = seed.conversation(c, "closed", age=100)
    seed.message(c, old_closed)
    seed.message(c, old_closed)
    report = await _run(env, _policy(message_days=90))
    assert report.counts == {"messages": 2, "conversations": 1}
    assert seed.count("clinic.message", c) == 0
    assert seed.count("clinic.conversation", c) == 0


async def test_open_and_recently_closed_conversations_keep_their_messages(env: ClinicEnv, seed: Seed) -> None:
    c = env.clinic_id
    open_conv = seed.conversation(c, "open", age=500)
    handoff = seed.conversation(c, "handoff", age=500)
    recent_closed = seed.conversation(c, "closed", age=10)
    for conv in (open_conv, handoff, recent_closed):
        seed.message(c, conv)
    report = await _run(env, _policy(message_days=90))
    assert report.counts == {"messages": 0, "conversations": 0}
    assert seed.count("clinic.message", c) == 3
    assert seed.count("clinic.conversation", c) == 3


async def test_zero_days_keeps_messages_and_conversations_of_any_age(env: ClinicEnv, seed: Seed) -> None:
    c = env.clinic_id
    conv = seed.conversation(c, "closed", age=2000)
    seed.message(c, conv)
    report = await _run(env, _policy(message_days=0))
    assert report.counts == {}
    assert set(report.disabled) >= {"messages", "conversations"}
    assert seed.count("clinic.message", c) == 1
    assert seed.count("clinic.conversation", c) == 1


@pytest.mark.parametrize("status", ["pending", "escalated"])
async def test_an_open_review_item_protects_its_conversation_and_messages(
    env: ClinicEnv, seed: Seed, status: str
) -> None:
    c = env.clinic_id
    conv = seed.conversation(c, "closed", age=500)
    item = seed.review_item(c, conv, status)
    seed.message(c, conv, review_item=item)
    seed.message(c, conv)
    report = await _run(env, _policy(message_days=90))
    assert report.counts == {"messages": 0, "conversations": 0}
    assert seed.count("clinic.message", c) == 2
    assert seed.count("clinic.review_item", c, f"status = '{status}'") == 1


async def test_a_decided_review_item_keeps_its_conversation_but_not_the_messages(
    env: ClinicEnv, seed: Seed
) -> None:
    c = env.clinic_id
    conv = seed.conversation(c, "closed", age=500)
    seed.review_item(c, conv, "approved")
    seed.message(c, conv)
    report = await _run(env, _policy(message_days=90))
    assert report.counts == {"messages": 1, "conversations": 0}
    assert seed.count("clinic.conversation", c) == 1, "the foreign key of the review item keeps the shell"
    assert seed.count("clinic.review_item", c) == 1


async def test_patients_appointments_consent_and_audit_are_never_touched(env: ClinicEnv, seed: Seed) -> None:
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
    seed.conversation(c, "closed", age=3000)
    everything = _policy(
        message_days=1, auth_session_days=1, link_code_days=1, link_attempt_days=1, history_days=1
    )
    report = await _run(env, everything)
    assert not report.failed
    assert seed.count("clinic.patient", c) == 1
    assert seed.count("clinic.appointment", c) == 1
    assert seed.count("clinic.consent", c) == 1
    assert seed.count("clinic.audit_log", c, "action = 'synthetic.event'") == 1


async def test_expired_dashboard_sessions_go_after_the_grace_period_and_valid_ones_stay(
    env: ClinicEnv, seed: Seed
) -> None:
    c = env.clinic_id
    user = seed.user(c)
    seed.auth_session(c, user, expired_days_ago=5)
    seed.auth_session(c, user, expired_days_ago=0)
    seed.auth_session(c, user, expired_days_ago=-3)
    report = await _run(env, _policy(auth_session_days=1))
    assert report.counts["auth_sessions"] == 1
    assert seed.count("clinic.auth_session", c) == 2


async def test_expired_or_spent_link_codes_go_and_a_live_code_stays(env: ClinicEnv, seed: Seed) -> None:
    c = env.clinic_id
    user = seed.user(c)
    patient = seed.patient(c)
    seed.link_code(c, patient, user, expired_days_ago=30)
    seed.link_code(c, patient, user, expired_days_ago=-1, used_days_ago=30)
    seed.link_code(c, patient, user, expired_days_ago=-1)
    seed.link_code(c, patient, user, expired_days_ago=2)
    report = await _run(env, _policy(link_code_days=7))
    assert report.counts["link_codes"] == 2
    assert seed.count("clinic.identity_link_code", c) == 2
    assert seed.count("clinic.patient", c) == 1


async def test_old_link_attempts_are_deleted_through_the_narrow_door_and_recent_ones_stay(
    env: ClinicEnv, seed: Seed
) -> None:
    c = env.clinic_id
    seed.link_attempt(c, 90)
    seed.link_attempt(c, 90)
    seed.link_attempt(c, 3)
    report = await _run(env, _policy(link_attempt_days=30))
    assert report.counts["link_attempts"] == 2
    assert seed.count("clinic.identity_link_attempt", c) == 1


async def test_the_link_attempt_door_refuses_a_cutoff_inside_the_rate_limit_window(
    env: ClinicEnv,
) -> None:
    async with env.db.session(env.clinic_id) as session:
        with pytest.raises(DBAPIError, match="older than one hour"):
            await session.execute(text("SELECT clinic_agent.retention_purge_link_attempts(now(), 10, false)"))


async def test_dry_run_counts_what_would_go_and_changes_nothing(env: ClinicEnv, seed: Seed) -> None:
    c = env.clinic_id
    user = seed.user(c)
    conv = seed.conversation(c, "closed", age=100)
    seed.message(c, conv)
    seed.auth_session(c, user, expired_days_ago=9)
    seed.link_attempt(c, 90)
    policy = _policy(message_days=90, auth_session_days=1, link_attempt_days=30)
    report = await _run(env, policy, dry_run=True)
    assert report.dry_run
    assert report.counts == {"messages": 1, "conversations": 1, "auth_sessions": 1, "link_attempts": 1}
    assert seed.count("clinic.message", c) == 1
    assert seed.count("clinic.conversation", c) == 1
    assert seed.count("clinic.auth_session", c) == 1
    assert seed.count("clinic.identity_link_attempt", c) == 1
    assert seed.count("clinic.audit_log", c, "action = 'retention.run'") == 0, "a dry run writes no audit row"


async def test_two_clinics_are_isolated_a_run_for_one_never_deletes_the_rows_of_the_other(
    env: ClinicEnv, seed: Seed
) -> None:
    other = seed.new_clinic()
    for clinic in (env.clinic_id, other):
        conv = seed.conversation(clinic, "closed", age=100)
        seed.message(clinic, conv)
        seed.auth_session(clinic, seed.user(clinic), expired_days_ago=9)
    report = await _run(env, _policy(message_days=90, auth_session_days=1))
    assert report.counts["messages"] == 1
    assert seed.count("clinic.message", env.clinic_id) == 0
    assert seed.count("clinic.message", other) == 1
    assert seed.count("clinic.auth_session", other) == 1
    runner = RetentionRunner(env.db, _policy(message_days=90, auth_session_days=1), scopes=(Scope.CLINIC,))
    await runner.run_clinics([other])
    assert seed.count("clinic.message", other) == 0

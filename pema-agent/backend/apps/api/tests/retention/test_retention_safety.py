"""Retention: dry run, audit row, advisory lock, two runners at once, clinic isolation, database rights.

New tests (no TS source), on a real Postgres with the real migrations.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from pema.conversation.media_store import MediaStore
from pema.conversation.pg_testing import ClinicEnv
from pema.retention.pg_testing import Seed
from pema.retention.policy import RetentionPolicy, Scope
from pema.retention.runner import RetentionRunner, RunStatus, lock_keys

pytestmark = pytest.mark.db

ALL_ON = RetentionPolicy(
    history_days=30,
    memory_days=30,
    message_days=30,
    usage_days=30,
    trace_days=7,
    media_days=7,
    job_run_days=30,
    auth_session_days=1,
    link_code_days=7,
    link_attempt_days=30,
    batch_size=50,
)


def _agent_runner(env: ClinicEnv, media: MediaStore | None = None) -> RetentionRunner:
    return RetentionRunner(env.worker_db, ALL_ON, media=media, scopes=(Scope.AGENT,))


async def test_dry_run_deletes_no_row_no_file_and_writes_no_audit_row(
    env: ClinicEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    file = media.root / str(env.clinic_id) / "media" / "acc-1" / "t-1" / "m1-0.jpg"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"synthetic")
    seed.history(env.clinic_id, age=40, images=["media/acc-1/t-1/m1-0.jpg"], n=2)
    seed.memory(env.clinic_id, age=40)
    seed.usage_turn(env.clinic_id, age=40)
    seed.job_run(env.clinic_id, "job-1", age=90)
    report = await _agent_runner(env, media).run_scope(env.clinic_id, Scope.AGENT, dry_run=True)
    assert report.dry_run
    assert not report.failed
    assert report.counts["history"] == 2
    assert report.counts["history_media_files"] == 2, "image references of the rows that would go"
    assert report.counts["memories"] == 1
    assert report.counts["trace_steps"] == 2
    assert report.counts["usage"] == 1
    assert report.counts["job_runs"] == 1
    assert seed.count("agent.history", env.clinic_id) == 2
    assert seed.count("agent.memories", env.clinic_id) == 1
    assert seed.count("agent.usage", env.clinic_id) == 1
    assert seed.count("agent.job_runs", env.clinic_id) == 1
    assert file.exists()
    assert seed.count("clinic.audit_log", env.clinic_id, "action = 'retention.run'") == 0


async def test_a_real_run_writes_one_summary_audit_row_with_counters_only(env: ClinicEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=40, n=3)
    seed.audit(env.clinic_id, age=3000)
    await _agent_runner(env).run_scope(env.clinic_id, Scope.AGENT)
    rows = await env.fetch(
        "SELECT actor_type, action, entity_type, entity_id, details FROM clinic.audit_log "
        "WHERE action = 'retention.run'"
    )
    assert len(rows) == 1, "one row per run and scope, written by the worker through the narrow function"
    row = rows[0]
    assert (row["actor_type"], row["entity_type"], row["entity_id"]) == ("system", "retention", "agent")
    raw = row["details"]
    details = cast("dict[str, Any]", raw if isinstance(raw, dict) else json.loads(str(raw)))
    assert details["scope"] == "agent"
    assert details["deleted"]["history"] == 3
    assert details["deleted"]["capped_groups"] == 0
    assert details["deleted"]["failed_groups"] == 0
    deleted: dict[str, Any] = details["deleted"]
    assert all(isinstance(v, int) for v in deleted.values()), "counters only, no text"
    assert seed.count("clinic.audit_log", env.clinic_id, "action = 'synthetic.event'") == 1, "audit is kept"


async def test_the_audit_door_refuses_free_text_and_unknown_scopes(env: ClinicEnv) -> None:
    for scope, counts in (
        ("agent", '{"note": "patient name"}'),
        ("agent", '{"history": "12"}'),
        ("agent", '{"history": -1}'),
        ("agent", '{"Bad Key": 1}'),
        ("agent", "[1]"),
        ("other", '{"history": 1}'),
    ):
        async with env.worker_db.session(env.clinic_id) as session:
            with pytest.raises(DBAPIError):
                await session.execute(
                    text("SELECT clinic_agent.record_retention_run(:s, CAST(:c AS jsonb))"),
                    {"s": scope, "c": counts},
                )


async def test_a_run_that_finds_the_advisory_lock_taken_does_nothing_and_says_so(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=3)
    first, second = lock_keys(env.clinic_id, Scope.AGENT)
    async with env.db.engine.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:a, :b)"), {"a": first, "b": second})
        blocked = await _agent_runner(env).run_scope(env.clinic_id, Scope.AGENT)
        # the other scope of the same clinic is a different lock
        other_scope = await RetentionRunner(env.db, ALL_ON, scopes=(Scope.CLINIC,)).run_scope(
            env.clinic_id, Scope.CLINIC
        )
        await holder.execute(text("SELECT pg_advisory_unlock(:a, :b)"), {"a": first, "b": second})
        await holder.rollback()
    assert blocked.status is RunStatus.SKIPPED_LOCKED
    assert blocked.counts == {}
    assert other_scope.status is RunStatus.DONE
    assert seed.count("agent.history", env.clinic_id) == 3
    freed = await _agent_runner(env).run_scope(env.clinic_id, Scope.AGENT)
    assert freed.status is RunStatus.DONE
    assert freed.counts["history"] == 3


async def test_the_lock_is_released_at_the_end_of_every_run(env: ClinicEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=40)
    runner = RetentionRunner(env.worker_db, ALL_ON, scopes=(Scope.AGENT,))
    first = await runner.run_scope(env.clinic_id, Scope.AGENT)
    again = await runner.run_scope(env.clinic_id, Scope.AGENT)
    assert first.status is RunStatus.DONE
    assert again.status is RunStatus.DONE


async def test_two_runners_at_the_same_time_do_not_fail_and_every_expired_row_is_deleted_once(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.history_bulk(env.clinic_id, age=40, n=1500)
    seed.history(env.clinic_id, age=2, n=5)
    one = _agent_runner(env)
    two = RetentionRunner(env.db, ALL_ON, scopes=(Scope.AGENT,))  # a second process, even another role
    reports = await asyncio.gather(
        one.run_scope(env.clinic_id, Scope.AGENT), two.run_scope(env.clinic_id, Scope.AGENT)
    )
    assert all(not r.failed for r in reports)
    assert sum(r.counts.get("history", 0) for r in reports) == 1500
    assert seed.count("agent.history", env.clinic_id) == 5
    done = [r for r in reports if r.status is RunStatus.DONE]
    assert done, "at least one of the two ran"


async def test_a_run_for_one_clinic_never_touches_the_rows_of_another_agent_scope(
    env: ClinicEnv, seed: Seed, tmp_path: Path
) -> None:
    other = seed.new_clinic()
    media = MediaStore(tmp_path / "volume")
    other_file = media.root / str(other) / "media" / "acc-1" / "t-1" / "m1-0.jpg"
    other_file.parent.mkdir(parents=True)
    other_file.write_bytes(b"synthetic")
    old = other_file.stat().st_mtime - 40 * 86400
    os.utime(other_file, (old, old))
    for clinic in (env.clinic_id, other):
        seed.history(clinic, age=40, images=["media/acc-1/t-1/m1-0.jpg"])
        seed.memory(clinic, age=40)
        seed.usage_turn(clinic, age=40)
    await _agent_runner(env, media).run_scope(env.clinic_id, Scope.AGENT)
    assert seed.count("agent.history", env.clinic_id) == 0
    assert seed.count("agent.history", other) == 1
    assert seed.count("agent.memories", other) == 1
    assert seed.count("agent.usage_steps", other) == 2
    assert other_file.exists(), "media of the other clinic is outside this run"
    await _agent_runner(env, media).run_clinics([other])
    assert seed.count("agent.history", other) == 0
    assert not other_file.exists()


async def test_the_worker_role_gained_no_right_on_clinic_tables(env: ClinicEnv) -> None:
    for table in ("message", "conversation", "auth_session", "identity_link_code", "audit_log"):
        async with env.worker_db.session(env.clinic_id) as session:
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(text(f"SELECT 1 FROM clinic.{table} LIMIT 1"))  # noqa: S608
    async with env.worker_db.session(env.clinic_id) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text("SELECT clinic_agent.retention_purge_link_attempts(now() - interval '2 days', 10, true)")
            )


async def test_not_even_the_api_role_can_delete_audit_rows(env: ClinicEnv, seed: Seed) -> None:
    seed.audit(env.clinic_id, age=3000)
    async with env.db.session(env.clinic_id) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(text("DELETE FROM clinic.audit_log"))

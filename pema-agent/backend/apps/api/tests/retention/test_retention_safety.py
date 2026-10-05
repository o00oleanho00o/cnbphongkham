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
from pema.retention.pg_testing import RetentionEnv, Seed
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


def _agent_runner(env: RetentionEnv, media: MediaStore | None = None) -> RetentionRunner:
    return RetentionRunner(env.worker_db, ALL_ON, media=media, scopes=(Scope.AGENT,))


async def test_dry_run_deletes_no_row_no_file_and_writes_no_audit_row(
    env: RetentionEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    file = media.root / str(env.clinic_id) / "media" / "acc-1" / "t-1" / "m1-0.jpg"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"synthetic")
    seed.history(env.clinic_id, age=40, images=["media/acc-1/t-1/m1-0.jpg"], n=2)
    seed.memory(env.clinic_id, age=40)
    seed.usage_turn(env.clinic_id, age=40)
    seed.job_run(env.clinic_id, "job-1", age=90)
    report = await _agent_runner(env, media).run_scope(Scope.AGENT, dry_run=True)
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


async def test_a_real_run_writes_one_summary_audit_row_with_counters_only(
    env: RetentionEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=3)
    seed.audit(env.clinic_id, age=3000)
    await _agent_runner(env).run_scope(Scope.AGENT)
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


async def test_the_audit_door_refuses_free_text_and_unknown_scopes(env: RetentionEnv) -> None:
    for scope, counts in (
        ("agent", '{"note": "patient name"}'),
        ("agent", '{"history": "12"}'),
        ("agent", '{"history": -1}'),
        ("agent", '{"Bad Key": 1}'),
        ("agent", "[1]"),
        ("other", '{"history": 1}'),
    ):
        async with env.worker_db.session() as session:
            with pytest.raises(DBAPIError):
                await session.execute(
                    text("SELECT clinic_agent.record_retention_run(:s, CAST(:c AS jsonb))"),
                    {"s": scope, "c": counts},
                )


async def test_a_run_that_finds_the_advisory_lock_taken_does_nothing_and_says_so(
    env: RetentionEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=3)
    first, second = lock_keys(Scope.AGENT)
    async with env.db.engine.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:a, :b)"), {"a": first, "b": second})
        blocked = await _agent_runner(env).run_scope(Scope.AGENT)
        # the other scope is a different lock
        other_scope = await RetentionRunner(env.db, ALL_ON, scopes=(Scope.CLINIC,)).run_scope(Scope.CLINIC)
        await holder.execute(text("SELECT pg_advisory_unlock(:a, :b)"), {"a": first, "b": second})
        await holder.rollback()
    assert blocked.status is RunStatus.SKIPPED_LOCKED
    assert blocked.counts == {}
    assert other_scope.status is RunStatus.DONE
    assert seed.count("agent.history", env.clinic_id) == 3
    freed = await _agent_runner(env).run_scope(Scope.AGENT)
    assert freed.status is RunStatus.DONE
    assert freed.counts["history"] == 3


async def test_the_lock_is_released_at_the_end_of_every_run(env: RetentionEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=40)
    runner = RetentionRunner(env.worker_db, ALL_ON, scopes=(Scope.AGENT,))
    first = await runner.run_scope(Scope.AGENT)
    again = await runner.run_scope(Scope.AGENT)
    assert first.status is RunStatus.DONE
    assert again.status is RunStatus.DONE


async def test_two_runners_at_the_same_time_do_not_fail_and_every_expired_row_is_deleted_once(
    env: RetentionEnv, seed: Seed
) -> None:
    seed.history_bulk(env.clinic_id, age=40, n=1500)
    seed.history(env.clinic_id, age=2, n=5)
    one = _agent_runner(env)
    two = RetentionRunner(env.db, ALL_ON, scopes=(Scope.AGENT,))  # a second process, even another role
    reports = await asyncio.gather(one.run_scope(Scope.AGENT), two.run_scope(Scope.AGENT))
    assert all(not r.failed for r in reports)
    assert sum(r.counts.get("history", 0) for r in reports) == 1500
    assert seed.count("agent.history", env.clinic_id) == 5
    done = [r for r in reports if r.status is RunStatus.DONE]
    assert done, "at least one of the two ran"


async def test_an_agent_run_deletes_the_expired_rows_and_media_files_of_the_installation_clinic_only(
    env: RetentionEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    expired = media.root / str(env.clinic_id) / "media" / "acc-1" / "t-1" / "m1-0.jpg"
    expired.parent.mkdir(parents=True)
    expired.write_bytes(b"synthetic")
    old = expired.stat().st_mtime - 40 * 86400
    os.utime(expired, (old, old))
    elsewhere = media.root / "not-the-clinic" / "media" / "acc-1" / "t-1" / "m2-0.jpg"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(b"synthetic")
    os.utime(elsewhere, (old, old))
    seed.history(env.clinic_id, age=40, images=["media/acc-1/t-1/m1-0.jpg"])
    seed.history(env.clinic_id, age=2)
    seed.memory(env.clinic_id, age=40)
    seed.usage_turn(env.clinic_id, age=40)
    report = await _agent_runner(env, media).run_scope(Scope.AGENT)
    assert report.clinic_id == env.clinic_id
    assert seed.count("agent.history", env.clinic_id) == 1
    assert seed.count("agent.memories", env.clinic_id) == 0
    assert seed.count("agent.usage_steps", env.clinic_id) == 0
    assert not expired.exists()
    assert elsewhere.exists(), "a directory that is not the clinic's is outside the run"


async def test_run_all_runs_every_scope_of_the_runner_once_for_the_installation_clinic(
    env: RetentionEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=2)
    seed.conversation(env.clinic_id, "closed", age=100)
    runner = RetentionRunner(env.db, ALL_ON)
    reports = await runner.run_all(dry_run=True)
    assert [r.scope for r in reports] == [Scope.AGENT, Scope.CLINIC]
    assert {r.clinic_id for r in reports} == {env.clinic_id}
    assert reports[0].counts["history"] == 2
    assert reports[1].counts["conversations"] == 1


async def test_the_lock_keys_are_fixed_per_scope_and_differ_between_scopes() -> None:
    assert lock_keys(Scope.AGENT) == lock_keys(Scope.AGENT)
    assert lock_keys(Scope.AGENT) != lock_keys(Scope.CLINIC)


async def test_the_worker_role_gained_no_right_on_clinic_tables(env: RetentionEnv) -> None:
    for table in ("message", "conversation", "auth_session", "identity_link_code", "audit_log"):
        async with env.worker_db.session() as session:
            with pytest.raises(DBAPIError, match="permission denied"):
                await session.execute(text(f"SELECT 1 FROM clinic.{table} LIMIT 1"))  # noqa: S608
    async with env.worker_db.session() as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                text("SELECT clinic_agent.retention_purge_link_attempts(now() - interval '2 days', 10, true)")
            )


async def test_not_even_the_api_role_can_delete_audit_rows(env: RetentionEnv, seed: Seed) -> None:
    seed.audit(env.clinic_id, age=3000)
    async with env.db.session() as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(text("DELETE FROM clinic.audit_log"))

"""Retention, scope ``agent``: ``agent.*`` rows and the media files, run as ``agent_worker`` (no right on ``clinic.*``).

New tests (no TS source). Every group: expired data goes, data inside its period stays, ``0`` days keeps all.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from pema.conversation.media_store import MediaStore
from pema.conversation.pg_testing import ClinicEnv
from pema.retention.pg_testing import Seed
from pema.retention.policy import RetentionPolicy, Scope
from pema.retention.runner import RetentionRunner, ScopeReport

pytestmark = pytest.mark.db

KEEP = RetentionPolicy(
    history_days=0,
    memory_days=0,
    message_days=0,
    usage_days=0,
    trace_days=0,
    media_days=0,
    job_run_days=0,
    auth_session_days=0,
    link_code_days=0,
    link_attempt_days=0,
    batch_size=100,
)


def _runner(env: ClinicEnv, policy: RetentionPolicy, media: MediaStore | None = None) -> RetentionRunner:
    return RetentionRunner(env.worker_db, policy, media=media, scopes=(Scope.AGENT,))


async def _run(env: ClinicEnv, policy: RetentionPolicy, media: MediaStore | None = None) -> ScopeReport:
    return await _runner(env, policy, media).run_scope(env.clinic_id, Scope.AGENT)


def _policy(**days: int) -> RetentionPolicy:
    values = {name: getattr(KEEP, name) for name in KEEP.__dataclass_fields__} | days
    return RetentionPolicy(**values)


def _write(media: MediaStore, env: ClinicEnv, rel_path: str, age_days: int) -> Path:
    path = media.root / str(env.clinic_id) / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"synthetic image bytes")
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))
    return path


async def test_history_older_than_the_period_is_deleted_and_newer_rows_stay(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=3)
    seed.history(env.clinic_id, age=10, n=2)
    report = await _run(env, _policy(history_days=30))
    assert report.counts["history"] == 3
    assert seed.count("agent.history", env.clinic_id) == 2
    assert seed.count("agent.history", env.clinic_id, "created_at < now() - interval '30 days'") == 0


async def test_zero_days_keeps_every_group_even_when_the_data_is_very_old(env: ClinicEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=900)
    seed.memory(env.clinic_id, age=900)
    seed.usage_turn(env.clinic_id, age=900)
    seed.job_run(env.clinic_id, "job-1", age=900)
    seed.image_description(env.clinic_id, "media/acc-1/t-1/old.jpg", age=900)
    seed.thread(env.clinic_id, "t-idle", last_message_age=900)
    report = await _run(env, KEEP)
    assert report.counts == {}
    assert {"history", "memories", "trace_steps", "usage", "job_runs", "image_descriptions"} <= set(
        report.disabled
    )
    assert seed.count("agent.history", env.clinic_id) == 1
    assert seed.count("agent.memories", env.clinic_id) == 1
    assert seed.count("agent.usage", env.clinic_id) == 1
    assert seed.count("agent.usage_steps", env.clinic_id) == 2
    assert seed.count("agent.job_runs", env.clinic_id) == 1
    assert seed.count("agent.image_descriptions", env.clinic_id) == 1
    assert seed.count("agent.threads", env.clinic_id, "summary <> ''") == 1


async def test_history_deletion_removes_the_image_files_and_descriptions_of_the_deleted_rows(
    env: ClinicEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    old_file = _write(media, env, "media/acc-1/t-1/m1-0.jpg", age_days=1)
    new_file = _write(media, env, "media/acc-1/t-2/m2-0.jpg", age_days=1)
    seed.history(env.clinic_id, age=40, images=["media/acc-1/t-1/m1-0.jpg"], thread="t-1")
    seed.history(env.clinic_id, age=2, images=["media/acc-1/t-2/m2-0.jpg"], thread="t-2")
    seed.image_description(env.clinic_id, "media/acc-1/t-1/m1-0.jpg", age=1)
    seed.image_description(env.clinic_id, "media/acc-1/t-2/m2-0.jpg", age=1)

    report = await _run(env, _policy(history_days=30), media)

    assert report.counts["history"] == 1
    assert report.counts["history_media_files"] == 1
    assert report.counts["image_descriptions"] == 1
    assert not old_file.exists()
    assert not old_file.parent.exists(), "the directory the file leaves empty goes too"
    assert new_file.exists()
    assert seed.count("agent.image_descriptions", env.clinic_id) == 1


async def test_a_path_that_escapes_the_media_directory_is_ignored(
    env: ClinicEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    outside = tmp_path / "volume" / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("not an image")
    seed.history(env.clinic_id, age=40, images=["../secret.txt", "media/../../secret.txt"])
    await _run(env, _policy(history_days=30), media)
    assert outside.exists()
    assert seed.count("agent.history", env.clinic_id) == 0


async def test_media_files_and_descriptions_older_than_media_days_go_and_newer_ones_stay(
    env: ClinicEnv, seed: Seed, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "volume")
    old = _write(media, env, "media/acc-1/t-1/old.jpg", age_days=20)
    new = _write(media, env, "media/acc-1/t-1/new.jpg", age_days=2)
    seed.image_description(env.clinic_id, "media/acc-1/t-1/old.jpg", age=20)
    seed.image_description(env.clinic_id, "media/acc-1/t-1/new.jpg", age=2)
    report = await _run(env, _policy(media_days=7), media)
    assert report.counts["media_files"] == 1
    assert report.counts["image_descriptions"] == 1
    assert not old.exists()
    assert new.exists()
    assert seed.count("agent.image_descriptions", env.clinic_id) == 1


async def test_summary_of_a_thread_idle_past_the_period_is_cleared_and_an_active_one_is_kept(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.thread(env.clinic_id, "t-idle", last_message_age=60)
    seed.thread(env.clinic_id, "t-active", last_message_age=3)
    seed.history(env.clinic_id, age=60, thread="t-idle")
    seed.history(env.clinic_id, age=3, thread="t-active")
    report = await _run(env, _policy(history_days=30))
    assert report.counts["thread_summaries"] == 1
    idle = await env.fetch(
        "SELECT summary, message_count, context_epoch FROM agent.threads WHERE thread_id = 't-idle'"
    )
    active = await env.fetch("SELECT summary FROM agent.threads WHERE thread_id = 't-active'")
    assert idle[0]["summary"] == ""
    assert idle[0]["message_count"] == 0
    assert idle[0]["context_epoch"] == 1
    assert active[0]["summary"] == "synthetic summary"
    again = await _run(env, _policy(history_days=30))
    assert again.counts.get("thread_summaries", 0) == 0, "idempotent: a cleared thread is not touched again"


async def test_memories_older_than_the_period_are_deleted(env: ClinicEnv, seed: Seed) -> None:
    seed.memory(env.clinic_id, age=100)
    seed.memory(env.clinic_id, age=5)
    report = await _run(env, _policy(memory_days=30))
    assert report.counts["memories"] == 1
    assert seed.count("agent.memories", env.clinic_id) == 1


async def test_trace_steps_expire_but_the_token_ledger_stays_while_usage_days_is_zero(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.usage_turn(env.clinic_id, age=20, steps=3)
    seed.usage_turn(env.clinic_id, age=2, steps=2)
    report = await _run(env, _policy(trace_days=7))
    assert report.counts["trace_steps"] == 3
    assert seed.count("agent.usage_steps", env.clinic_id) == 2
    assert seed.count("agent.usage", env.clinic_id) == 2, "the ledger holds no text and keeps its own clock"


async def test_usage_days_deletes_the_ledger_and_its_steps_by_cascade(env: ClinicEnv, seed: Seed) -> None:
    seed.usage_turn(env.clinic_id, age=400, steps=2)
    seed.usage_turn(env.clinic_id, age=2, steps=2)
    report = await _run(env, _policy(usage_days=365))
    assert report.counts["usage"] == 1
    assert seed.count("agent.usage", env.clinic_id) == 1
    assert seed.count("agent.usage_steps", env.clinic_id) == 2


async def test_old_job_runs_are_deleted_but_a_running_row_never(env: ClinicEnv, seed: Seed) -> None:
    seed.job_run(env.clinic_id, "job-1", age=90, status="ok")
    seed.job_run(env.clinic_id, "job-1", age=90, status="error")
    seed.job_run(env.clinic_id, "job-1", age=90, status="running")
    seed.job_run(env.clinic_id, "job-1", age=3, status="ok")
    report = await _run(env, _policy(job_run_days=30))
    assert report.counts["job_runs"] == 2
    assert seed.count("agent.job_runs", env.clinic_id) == 2
    assert seed.count("agent.job_runs", env.clinic_id, "status = 'running'") == 1
    assert seed.count("agent.jobs", env.clinic_id) == 1, "the job itself (a promise to the patient) stays"


async def test_a_second_run_deletes_nothing_more(env: ClinicEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=40, n=4)
    seed.memory(env.clinic_id, age=40)
    policy = _policy(history_days=30, memory_days=30)
    first = await _run(env, policy)
    second = await _run(env, policy)
    assert first.counts["history"] == 4
    assert first.counts["memories"] == 1
    assert second.counts.get("history", 0) == 0
    assert second.counts.get("memories", 0) == 0
    assert not second.failed


async def test_work_is_done_in_batches_and_a_group_that_hits_the_cap_says_so(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=7)
    runner = RetentionRunner(
        env.worker_db, _policy(history_days=30, batch_size=2), scopes=(Scope.AGENT,), max_batches=2
    )
    first = await runner.run_scope(env.clinic_id, Scope.AGENT)
    assert first.counts["history"] == 4
    assert first.capped == ["history"]
    assert seed.count("agent.history", env.clinic_id) == 3
    second = await runner.run_scope(env.clinic_id, Scope.AGENT)
    third = await runner.run_scope(env.clinic_id, Scope.AGENT)
    assert second.counts["history"] == 3
    assert second.capped == []
    assert third.counts["history"] == 0
    assert seed.count("agent.history", env.clinic_id) == 0

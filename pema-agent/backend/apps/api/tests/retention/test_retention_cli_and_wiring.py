"""Retention: policy from settings, the periodic loop, the command line, the wiring and the migration chain.

New tests (no TS source). The command-line tests need Postgres (marker ``db``); the rest run without it.
"""

from __future__ import annotations

import asyncio
import io
import re
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import ValidationError

from pema.config.env import Settings
from pema.conversation.pg_testing import BE_PASSWORD, WORKER_PASSWORD, ClinicEnv
from pema.core.db import ClinicDatabase
from pema.retention.pg_testing import Seed
from pema.retention.policy import RetentionPolicy, Scope, policy_from_settings
from pema.retention.runner import RetentionRunner, RunStatus, ScopeReport
from pema.retention.schedule import start_retention_loop
from pema.workers.retention import format_report, run_cli

API_DIR = Path(__file__).resolve().parents[2]
PEMA = API_DIR / "pema"
ENV_EXAMPLE = Path(__file__).resolve().parents[5] / "infra" / ".env.example"


def _tuning(values: dict[str, int]) -> Callable[[str], int]:
    def read(key: str) -> int:
        return values[key]

    return read


# ------------------------------------------------------------------------------------------------ policy
def test_defaults_keep_clinical_data_and_messages_and_give_technical_data_a_short_life() -> None:
    policy = policy_from_settings(
        Settings(), _tuning({"AGENT_TRACE_RETENTION_DAYS": 7, "MEDIA_RETENTION_DAYS": 7})
    )
    assert (policy.history_days, policy.memory_days, policy.message_days, policy.usage_days) == (0, 0, 0, 0)
    assert policy.trace_days == 7
    assert policy.media_days == 7
    assert policy.job_run_days > 0
    assert policy.auth_session_days > 0
    assert policy.link_code_days > 0
    assert policy.link_attempt_days > 0


def test_trace_and_media_follow_the_tuning_keys_until_a_retention_setting_overrides_them() -> None:
    tuning = _tuning({"AGENT_TRACE_RETENTION_DAYS": 14, "MEDIA_RETENTION_DAYS": 21})
    followed = policy_from_settings(Settings(), tuning)
    assert (followed.trace_days, followed.media_days) == (14, 21)
    overridden = policy_from_settings(Settings(retention_trace_days=0, retention_media_days=3), tuning)
    assert (overridden.trace_days, overridden.media_days) == (0, 3), "0 keeps forever, also for these two"


def test_a_negative_number_of_days_is_refused_by_the_settings_and_by_the_policy() -> None:
    with pytest.raises(ValidationError):
        Settings(retention_history_days=-1)
    with pytest.raises(ValueError, match="history_days"):
        RetentionPolicy(history_days=-1)
    with pytest.raises(ValueError, match="batch_size"):
        RetentionPolicy(batch_size=0)


def test_every_retention_setting_is_documented_in_the_env_example() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in Settings.model_fields:
        if name.startswith("retention_"):
            assert f"PEMA_{name.upper()}=" in text, f"PEMA_{name.upper()} missing in infra/.env.example"


# ---------------------------------------------------------------------------------------------- the loop
class _CountingRunner(RetentionRunner):
    def __init__(self, fail_first: bool = False) -> None:
        super().__init__(ClinicDatabase("postgresql+psycopg://x:y@127.0.0.1:1/none"), RetentionPolicy())
        self.passes = 0
        self._fail_first = fail_first

    async def run_active_clinics(self, *, dry_run: bool = False) -> list[ScopeReport]:
        self.passes += 1
        if self._fail_first and self.passes == 1:
            raise RuntimeError("database is down")
        return []


async def test_a_zero_interval_turns_the_periodic_run_off() -> None:
    assert start_retention_loop(_CountingRunner(), interval_seconds=0) is None


async def test_the_loop_runs_every_interval_and_a_failing_pass_does_not_stop_it() -> None:
    runner = _CountingRunner(fail_first=True)
    task = start_retention_loop(runner, interval_seconds=0.01, initial_delay_seconds=0.01)
    assert task is not None
    for _ in range(200):
        if runner.passes >= 3:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runner.passes >= 3, "the first pass raised and the loop went on"


# ------------------------------------------------------------------------------------------------ wiring
def test_the_worker_runs_the_agent_scope_and_the_api_process_the_clinic_scope() -> None:
    worker = (PEMA / "workers" / "main.py").read_text(encoding="utf-8")
    api = (PEMA / "composition" / "api_wiring.py").read_text(encoding="utf-8")
    assert "scopes=(Scope.AGENT,)" in worker
    assert "Scope.CLINIC" not in worker
    assert "scopes=(Scope.CLINIC,)" in api
    assert "Scope.AGENT" not in api
    assert "start_media_cleanup_schedule" not in worker, "the retention run replaces the former daily cleanup"
    assert "pema.workers.retention" not in api, "the API process never imports the worker package"


def test_the_migration_chain_has_one_head() -> None:
    heads = ScriptDirectory.from_config(Config(str(API_DIR / "alembic.ini"))).get_heads()
    assert heads == ["h2_0007_retention"]


def test_no_retention_sql_names_the_audit_log_in_a_delete() -> None:
    for module in ("rules.py", "runner.py"):
        source = (PEMA / "retention" / module).read_text(encoding="utf-8")
        assert not re.search(r"DELETE\s+FROM\s+clinic\.audit_log", source, re.IGNORECASE)


# ------------------------------------------------------------------------------------------ command line
def _settings(env: ClinicEnv, *, history_days: int = 0, message_days: int = 0) -> Settings:
    return Settings(
        database_url=env.server.role_url("be_app", BE_PASSWORD),
        worker_database_url=env.server.role_url("agent_worker", WORKER_PASSWORD),
        retention_history_days=history_days,
        retention_message_days=message_days,
    )


@pytest.mark.db
async def test_cli_dry_run_for_one_clinic_prints_the_counts_and_changes_nothing(
    env: ClinicEnv, seed: Seed
) -> None:
    seed.history(env.clinic_id, age=40, n=2)
    seed.conversation(env.clinic_id, "closed", age=100)
    out = io.StringIO()
    code = await run_cli(
        ["--dry-run", "--clinic", str(env.clinic_id)],
        settings=_settings(env, history_days=30, message_days=90),
        out=out,
    )
    printed = out.getvalue()
    assert code == 0
    assert f"clinic {env.clinic_id} scope=agent" in printed
    assert f"clinic {env.clinic_id} scope=clinic" in printed
    assert "would delete history: 2" in printed
    assert "would delete conversations: 1" in printed
    assert seed.count("agent.history", env.clinic_id) == 2
    assert seed.count("clinic.conversation", env.clinic_id) == 1


@pytest.mark.db
async def test_cli_agent_scope_connects_as_the_worker_role_and_deletes(env: ClinicEnv, seed: Seed) -> None:
    seed.history(env.clinic_id, age=40, n=2)
    settings = _settings(env, history_days=30).model_copy(
        update={"database_url": "postgresql+psycopg://be_app:wrong@127.0.0.1:1/none"}
    )
    out = io.StringIO()
    code = await run_cli(["--scope", "agent", "--clinic", str(env.clinic_id)], settings=settings, out=out)
    assert code == 0, out.getvalue()
    assert "deleted history: 2" in out.getvalue()
    assert seed.count("agent.history", env.clinic_id) == 0


@pytest.mark.db
async def test_cli_without_clinic_visits_every_active_clinic(env: ClinicEnv, seed: Seed) -> None:
    other = seed.new_clinic()
    seed.history(env.clinic_id, age=40)
    seed.history(other, age=40)
    out = io.StringIO()
    code = await run_cli(["--scope", "clinic"], settings=_settings(env, history_days=30), out=out)
    assert code == 0
    assert f"clinic {other} scope=clinic" in out.getvalue()
    assert f"clinic {env.clinic_id} scope=clinic" in out.getvalue()


def test_the_report_of_a_skipped_run_says_why() -> None:
    report = ScopeReport(uuid.uuid4(), Scope.AGENT, False, status=RunStatus.SKIPPED_LOCKED)
    assert "another runner holds the lock" in format_report(report)

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
from pema.core.db import ClinicDatabase
from pema.core.pg_testing import BE_PASSWORD
from pema.retention.cli import format_report, run_cli
from pema.retention.pg_testing import RetentionEnv, Seed
from pema.retention.policy import RetentionPolicy, Scope, policy_from_settings
from pema.retention.runner import RetentionRunner, RunStatus, ScopeReport
from pema.retention.schedule import start_retention_loop

API_DIR = Path(__file__).resolve().parents[2]
PEMA = API_DIR / "pema"
ENV_EXAMPLE = Path(__file__).resolve().parents[5] / "infra" / ".env.example"


def _tuning(values: dict[str, int]) -> Callable[[str], int]:
    def read(key: str) -> int:
        return values[key]

    return read


# ------------------------------------------------------------------------------------------------ policy
def test_defaults_give_expired_sessions_a_short_life() -> None:
    policy = policy_from_settings(Settings())
    assert policy.auth_session_days > 0


def test_a_negative_number_of_days_is_refused_by_the_settings_and_by_the_policy() -> None:
    with pytest.raises(ValidationError):
        Settings(retention_auth_session_days=-1)
    with pytest.raises(ValueError, match="auth_session_days"):
        RetentionPolicy(auth_session_days=-1)
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

    async def run_all(self, *, dry_run: bool = False) -> list[ScopeReport]:
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


def test_the_migration_chain_has_one_head() -> None:
    heads = ScriptDirectory.from_config(Config(str(API_DIR / "alembic.ini"))).get_heads()
    assert len(heads) == 1, heads


def test_no_retention_sql_names_the_audit_log_in_a_delete() -> None:
    for module in ("rules.py", "runner.py"):
        source = (PEMA / "retention" / module).read_text(encoding="utf-8")
        assert not re.search(r"DELETE\s+FROM\s+clinic\.audit_log", source, re.IGNORECASE)


# ------------------------------------------------------------------------------------------ command line
def _settings(env: RetentionEnv) -> Settings:
    return Settings(database_url=env.server.role_url("be_app", BE_PASSWORD))


@pytest.mark.db
async def test_cli_dry_run_prints_the_counts_and_changes_nothing(env: RetentionEnv, seed: Seed) -> None:
    seed.auth_session(env.clinic_id, seed.user(env.clinic_id), expired_days_ago=9)
    out = io.StringIO()
    code = await run_cli(
        ["--dry-run"],
        settings=_settings(env),
        out=out,
    )
    printed = out.getvalue()
    assert code == 0
    assert "scope=clinic status=done" in printed
    assert "scope=agent" not in printed
    assert "would delete auth_sessions: 1" in printed
    assert seed.count("clinic.auth_session", env.clinic_id) == 1


@pytest.mark.db
async def test_cli_has_no_clinic_option_one_installation_is_one_clinic(env: RetentionEnv, seed: Seed) -> None:
    with pytest.raises(SystemExit):
        await run_cli(["--clinic", str(env.clinic_id)], settings=_settings(env), out=io.StringIO())
    out = io.StringIO()
    code = await run_cli([], settings=_settings(env), out=out)
    assert code == 0
    assert "scope=clinic status=done" in out.getvalue()
    assert "scope=agent" not in out.getvalue()


def test_the_report_of_a_skipped_run_says_why() -> None:
    report = ScopeReport(uuid.uuid4(), Scope.CLINIC, False, status=RunStatus.SKIPPED_LOCKED)
    assert "another runner holds the lock" in format_report(report)

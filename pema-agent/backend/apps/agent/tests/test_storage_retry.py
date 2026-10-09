"""Retrying after a dropped database connection, without Postgres: only connection errors are retried, once,
and a version-checked note write whose outcome is unknown is settled by reading it back."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from agent_app import storage
from agent_app.storage import AgentDatabase, PostgresMemoryBackend, retrying
from agentcore.memory import MemoryKey, StoredNotes

KEY = MemoryKey("t", "dev", "agent")


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "RETRY_DELAY_S", 0.0)


def _dropped() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))


async def test_a_connection_error_is_retried_once() -> None:
    attempts: list[int] = []

    async def flaky() -> str:
        attempts.append(1)
        if len(attempts) == 1:
            raise _dropped()
        return "ok"

    assert await retrying("read", flaky) == "ok"
    assert len(attempts) == 2


async def test_a_second_connection_error_and_other_errors_go_up() -> None:
    attempts: list[int] = []

    async def down() -> str:
        attempts.append(1)
        raise _dropped()

    async def conflict() -> str:
        attempts.append(1)
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    with pytest.raises(OperationalError):
        await retrying("read", down)
    with pytest.raises(IntegrityError):
        await retrying("write", conflict)
    assert len(attempts) == 3


class _NotesEngine:
    """Stands in for the engine: a write fails with a dropped connection, after committing or not."""

    def __init__(self, *, commits: bool) -> None:
        self.stored = StoredNotes(text="old", version=1)
        self._commits = commits

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[SimpleNamespace]:
        async def execute(statement: Any, params: dict[str, Any]) -> None:
            if self._commits:
                self.stored = StoredNotes(text=params["content"], version=params["version"] + 1)
            raise _dropped()

        yield SimpleNamespace(execute=execute)

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[SimpleNamespace]:
        async def execute(statement: Any, params: dict[str, Any]) -> SimpleNamespace:
            row = SimpleNamespace(content=self.stored.text, version=self.stored.version)
            return SimpleNamespace(one_or_none=lambda: row)

        yield SimpleNamespace(execute=execute)


def _backend(engine: _NotesEngine) -> PostgresMemoryBackend:
    return PostgresMemoryBackend(cast(AgentDatabase, SimpleNamespace(engine=engine)))


@pytest.mark.parametrize("commits", [True, False])
async def test_a_note_write_with_an_unknown_outcome_reports_what_happened(commits: bool) -> None:
    engine = _NotesEngine(commits=commits)

    saved = await _backend(engine).save(KEY, "new", expected_version=1)

    assert saved is commits
    assert engine.stored == (
        StoredNotes(text="new", version=2) if commits else StoredNotes(text="old", version=1)
    )

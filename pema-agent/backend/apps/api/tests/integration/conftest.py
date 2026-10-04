"""Fixtures of the closed-loop integration tests (package G).

They need a throwaway Postgres with pgvector (``PEMA_TEST_DATABASE_URL``, a superuser URL) AND a throwaway
Redis (``PEMA_TEST_REDIS_URL``); without either the tests are skipped. The database fixtures are the ones of
``pema.api.clinic_testing`` (migrated to ``heads`` once, two roles, a seeded demo clinic).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from pema.api.clinic_testing import (
    admin,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    worker_db,
    world_a,
    world_b,
)
from pema.channels.zalo_bot.settings import get_zalo_bot_settings
from pema.clinic.actions.seed_demo import SeedResult
from pema.composition.testing import TEST_ENCRYPTION_KEY, Loop, LoopFactory
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase

__all__ = [
    "admin",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "loop_env",
    "make_loop",
    "pg_url",
    "redis_url",
    "worker_db",
    "world_a",
    "world_b",
]


@pytest.fixture
def redis_url() -> str:
    url = os.environ.get("PEMA_TEST_REDIS_URL")
    if not url:
        pytest.skip("PEMA_TEST_REDIS_URL not set; no Redis to test against")
    return url


@pytest.fixture
def loop_env(monkeypatch: pytest.MonkeyPatch, jwt_env: None) -> Iterator[None]:
    """Environment of one loop: webhook mode, a synthetic encryption key, no human-like delays."""
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", TEST_ENCRYPTION_KEY)
    monkeypatch.setenv("PEMA_ZALO_BOT_MODE", "webhook")
    monkeypatch.setenv("PEMA_ZALO_BOT_WEBHOOK_BASE_URL", "https://cskh.example.test")
    for key, value in {
        "MESSAGE_BATCH_DEBOUNCE_MS": "0",
        "SEND_DELAY_MIN_MS": "0",
        "SEND_DELAY_MAX_MS": "0",
        "SCHEDULER_SEND_GAP_MS": "0",
        "LLM_API_KEY": "synthetic-not-used",
        "LLM_MODEL": "synthetic-model",
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    get_zalo_bot_settings.cache_clear()
    yield
    get_settings.cache_clear()
    get_zalo_bot_settings.cache_clear()


@pytest.fixture
def make_loop(
    loop_env: None,
    db: ClinicDatabase,
    worker_db: ClinicDatabase,
    world_a: SeedResult,
    redis_url: str,
    tmp_path: Path,
) -> LoopFactory:
    return LoopFactory(db, worker_db, world_a, redis_url, tmp_path)


__all__ += ["Loop"]

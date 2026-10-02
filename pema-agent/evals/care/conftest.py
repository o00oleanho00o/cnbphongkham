"""Fixtures of the care eval tests: the throwaway Postgres of the clinic tests (``db``, ``world``), skipped
without ``PEMA_TEST_DATABASE_URL``. ``evals/conftest.py`` puts ``pema-agent/`` on ``sys.path``."""

from __future__ import annotations

from pema.api.clinic_testing import admin, db, demo_clock, pg_url, world
from pema.core.event_loop import ensure_selector_event_loop_policy

ensure_selector_event_loop_policy()

__all__ = ["admin", "db", "demo_clock", "pg_url", "world"]

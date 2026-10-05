"""Fixtures of the package-M tests. They live in ``pema.api.clinic_testing`` (shared with ``tests/clinic``)."""

from __future__ import annotations

from pema.api.clinic_testing import admin, db, demo_clock, pg_url, worker_db, world

__all__ = ["admin", "db", "demo_clock", "pg_url", "worker_db", "world"]

"""Fixtures of the clinic tests. They live in ``pema.api.clinic_testing`` (shared with ``tests/api``)."""

from __future__ import annotations

from pema.api.clinic_testing import (
    admin,
    app,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    worker_db,
    world,
)

__all__ = [
    "admin",
    "app",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "pg_url",
    "worker_db",
    "world",
]

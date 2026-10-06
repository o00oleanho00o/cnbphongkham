"""Fixtures of the ops eval tests: the throwaway Postgres of the clinic tests (``db``, ``world``, ``admin``,
``client_factory``), skipped without ``PEMA_TEST_DATABASE_URL``. ``evals/conftest.py`` puts ``pema-agent/`` on
``sys.path``. ``staff_ctx`` and ``add_account`` are the helpers of ``backend/apps/api/tests/ops/conftest.py``,
copied here because the two test trees are collected separately."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.engine import Engine

from evals.ops.db_support import ensure_operators, insert_account, staff_context
from pema.api.clinic_testing import (
    admin,
    app,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    world,
)
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema_contracts.actions import ActionContext

ensure_selector_event_loop_policy()

__all__ = [
    "add_account",
    "admin",
    "app",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "operators",
    "pg_url",
    "staff_ctx",
    "world",
]

AddAccount = Callable[..., str]
StaffCtx = Callable[[str], ActionContext]


@pytest.fixture
def add_account(admin: Engine, world: SeedResult) -> AddAccount:
    """``add_account("long", purpose="customer", ...)`` inserts a channel account and returns its id."""

    def make(
        account_id: str, *, channel: str = "zalo_personal", purpose: str = "customer", **columns: Any
    ) -> str:
        return insert_account(admin, world, account_id, channel=channel, purpose=purpose, **columns)

    return make


@pytest.fixture
def operators(admin: Engine, world: SeedResult) -> None:
    """The fifth operator of ``OPERATOR_KEYS`` (a CS user added to the seed)."""
    ensure_operators(admin, world)


@pytest.fixture
def staff_ctx(world: SeedResult) -> StaffCtx:
    """``staff_ctx("manager")``: the action context of a seeded user (the role follows the seed)."""
    return lambda key: staff_context(world, key)

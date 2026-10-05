"""Event loop policy for psycopg async on Windows.

``psycopg`` (the async Postgres driver used through SQLAlchemy) cannot run on the default Windows
``ProactorEventLoop``. Developers on Windows call ``ensure_selector_event_loop_policy()`` BEFORE the loop
starts (entry points of the worker, ``tests/conftest.py``); for the API use
``uvicorn --factory pema.bootstrap:create_app`` under WSL or call it from a tiny launcher. The production
target is Ubuntu (PLAN-AI01 section 8) where this is a no-op.
"""

from __future__ import annotations

import asyncio
import sys


def ensure_selector_event_loop_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined,unused-ignore]

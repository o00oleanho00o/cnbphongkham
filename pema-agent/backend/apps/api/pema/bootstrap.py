"""Composition root: the only module allowed to wire api, workers and channels together.

``create_app()`` is cheap and needs neither Redis nor a database (the OpenAPI export and most tests call it
bare). The real objects are built in the ``lifespan`` of the app, once per process, by ``pema.composition``:
the runtime (stores, policy, tools, engine, scheduler), the intake stacks of the two Zalo channels and the
installation into the routers (``wire_api``). The worker is the other process: ``pema.workers.main``.

A bare ``create_app()`` served with no lifespan (a test with ``httpx.ASGITransport``) leaves every seam
unwired, so the routers fail closed exactly as before: 401 without a session, 501/503 where a service is
missing.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import FastAPI

from pema.api.body_limit import BodyLimitMiddleware
from pema.api.errors import install_error_handlers
from pema.api.router import TAGS_METADATA, build_api_router, build_system_router, unique_operation_id
from pema.composition.app_runtime import AppLifecycle, AppRuntime, build_app_runtime, wire_app
from pema.composition.auth_bridge import StaffSessionMiddleware
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase
from pema.shared.logger import configure_logging
from pema_contracts import __version__

API_TITLE = "Pema Clinic API"
API_DESCRIPTION = (
    "Backend of the Pema Digital Clinic: authentication, CRM, Inbox and knowledge base. "
    "All timestamps are ISO 8601 with +07:00. Errors use ErrorResponse with a stable ErrorCode. "
    "Mutating endpoints that accept an Idempotency-Key replay the first result for the same key. "
    "Staff endpoints need the session cookie of POST /auth/login; the permission of each role follows the "
    "matrix of docs/ARCH-PB01.md and a missing session or permission is refused (401, 403)."
)


@lru_cache
def _default_database(url: str) -> ClinicDatabase:
    """The database of a bare app (no lifespan, ``app.state.clinic_db`` not set): one per URL, never one per
    request."""
    return ClinicDatabase(url)


def create_app(*, runtime: AppRuntime | None = None) -> FastAPI:
    """``runtime`` is for the integration tests (their own database); production passes none and the lifespan
    builds everything from the environment."""
    settings = get_settings()
    configure_logging(
        settings.log_level,
        file_enabled=settings.log_file_enabled,
        log_dir=settings.log_dir,
        keep_days=settings.log_file_keep_days,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        lifecycle: AppLifecycle | None = None
        if getattr(app.state, "runtime", None) is None:
            rt = runtime or build_app_runtime(settings)
            wire_app(app, rt)
            lifecycle = AppLifecycle(rt)
            await lifecycle.start()
        try:
            yield
        finally:
            if lifecycle is not None:
                await lifecycle.stop()

    # The interactive docs and the schema describe every route to whoever can reach the API: only in ``dev``.
    docs_open = settings.environment == "dev"
    app = FastAPI(
        docs_url="/docs" if docs_open else None,
        redoc_url="/redoc" if docs_open else None,
        openapi_url="/openapi.json" if docs_open else None,
        title=API_TITLE,
        version=__version__,
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        generate_unique_id_function=unique_operation_id,
        separate_input_output_schemas=False,
        lifespan=lifespan,
    )

    def current_db() -> ClinicDatabase:
        configured: object = getattr(app.state, "clinic_db", None)
        if isinstance(configured, ClinicDatabase):
            return configured
        return _default_database(settings.database_url)

    install_error_handlers(app)
    app.add_middleware(
        StaffSessionMiddleware,
        db=current_db,
        enforce=lambda: getattr(app.state, "runtime", None) is not None,
    )
    # Added LAST = outermost: the body ceiling is applied before anything reads a body.
    app.add_middleware(BodyLimitMiddleware)
    app.include_router(build_system_router())
    app.include_router(build_api_router())
    return app

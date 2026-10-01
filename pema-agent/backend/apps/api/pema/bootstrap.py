"""Composition root: the only module allowed to wire api, workers and channels together."""

from __future__ import annotations

from fastapi import FastAPI

from pema.api.errors import install_error_handlers
from pema.api.router import TAGS_METADATA, build_api_router, build_system_router, unique_operation_id
from pema.config.env import get_settings
from pema.shared.logger import configure_logging
from pema_contracts import __version__

API_TITLE = "Pema CSKH Agent API"
API_DESCRIPTION = (
    "Backend of the Pema Digital Clinic CSKH agent (clinic CRM + a Python derivative of zalo-agent). "
    "All timestamps are ISO 8601 with +07:00. Errors use ErrorResponse with a stable ErrorCode. "
    "Mutating endpoints that accept an Idempotency-Key replay the first result for the same key. "
    "Skeleton phase: every endpoint except /healthz returns 501."
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        file_enabled=settings.log_file_enabled,
        log_dir=settings.log_dir,
        keep_days=settings.log_file_keep_days,
    )
    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        generate_unique_id_function=unique_operation_id,
        separate_input_output_schemas=False,
    )
    install_error_handlers(app)
    app.include_router(build_system_router())
    app.include_router(build_api_router())
    return app

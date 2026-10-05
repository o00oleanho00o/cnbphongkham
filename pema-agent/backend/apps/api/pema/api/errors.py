"""Exception handlers: every error leaves the API as ``ErrorResponse`` with a stable ``ErrorCode``."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pema.api.request_id import clean_request_id
from pema.shared.logger import create_logger
from pema_contracts.errors import DomainError, ErrorBody, ErrorCode, ErrorResponse

_log = create_logger("api.errors")


def _request_id(request: Request) -> str | None:
    return clean_request_id(request.headers.get("x-request-id"))


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    body = exc.to_response(_request_id(request))
    return JSONResponse(status_code=exc.http_status, content=body.model_dump(mode="json"))


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Only field locations and error types are returned; input values may contain PII.
    fields = [{"loc": [str(p) for p in e["loc"]], "type": e["type"]} for e in exc.errors()]
    body = ErrorResponse(
        error=ErrorBody(
            code=ErrorCode.VALIDATION_FAILED,
            message="Dữ liệu gửi lên không hợp lệ.",
            details={"fields": fields},
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.error("unhandled error", error_type=type(exc).__name__)
    body = ErrorResponse(
        error=ErrorBody(
            code=ErrorCode.INTERNAL,
            message="Lỗi hệ thống. Vui lòng thử lại.",
            request_id=_request_id(request),
        )
    )
    return JSONResponse(status_code=500, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)

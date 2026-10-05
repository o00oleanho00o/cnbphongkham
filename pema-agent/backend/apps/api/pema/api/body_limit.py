"""Ceiling on the size of a request body (package G, SECURITY-REVIEW-AI01 SEC-17; no zalo-agent source).

The two webhooks are public: they parse a JSON body BEFORE they can check a secret or a signature, and uvicorn
puts no ceiling on a body, so one anonymous client could make the API process gather gigabytes. A pure
ASGI middleware cuts the body at the reading layer, the moment the ceiling is crossed (a declared
``Content-Length`` is refused without reading a byte; a chunked body is counted as it arrives).

The knowledge-base upload and text routes are exempt: they carry documents up to ``KB_MAX_FILE_MB`` and have
their own cut (``kb_route_guards.KbBodyLimitRoute``). Everything else is small JSON.
"""

from __future__ import annotations

from typing import Final

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pema_contracts.errors import DomainError, ErrorCode

MAX_BODY_BYTES: Final = 4 * 1024 * 1024
EXEMPT_SUFFIXES: Final = ("/admin/kb/sources/file", "/admin/kb/sources/text")


class _BodyTooLargeError(BaseException):
    """A BaseException on purpose: FastAPI turns an ``Exception`` raised while reading the body into a 400."""


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or str(scope["path"]).endswith(EXEMPT_SUFFIXES):
            await self.app(scope, receive, send)
            return
        for key, value in scope.get("headers", []):
            if key == b"content-length" and value.isdigit() and int(value) > self._max:
                await self._refuse(scope, receive, send)
                return
        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    raise _BodyTooLargeError
            return message

        async def watching_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, watching_send)
        except _BodyTooLargeError:
            if not started:
                await self._refuse(scope, receive, send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        error = DomainError(ErrorCode.PAYLOAD_TOO_LARGE, "Nội dung gửi lên quá lớn.")
        response = JSONResponse(
            status_code=error.http_status, content=error.to_response(None).model_dump(mode="json")
        )
        await response(scope, receive, send)

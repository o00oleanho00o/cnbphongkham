"""The signing forwarder (docs/PLAN-crm-plugin.md 3.9).

The agent calls ``/agent-gateway/<path>`` here, without any credential. If (method, path) is one of the eight
routes of ``routes.py``, the service signs a fresh short token for exactly the permission of that route and
sends the call on to the CRM, then returns the CRM's answer as it is. Anything else is a 404 and never reaches
the CRM. Only a few headers travel in and a few travel back; redirects are never followed; each call leaves
one log line (route shape, status, milliseconds: no id, body, name or phone).
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable
from typing import Final
from uuid import uuid4

import httpx
import jwt
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from crm_signer.keys import SigningKey
from crm_signer.routes import match

log = logging.getLogger("crm_signer")

ISSUER: Final = "pema-crm-signer"
AUDIENCE: Final = "pema-agent-gateway"
ALGORITHM: Final = "EdDSA"
TOKEN_TTL_S: Final = 60
PER_MINUTE: Final = 300
MAX_BODY: Final = 64 * 1024
MAX_QUERY: Final = 512
UPSTREAM_TIMEOUT_S: Final = 15.0
PREFIX: Final = "/agent-gateway"
FORWARD_IN: Final = ("content-type", "idempotency-key", "x-request-id")
FORWARD_BACK: Final = ("content-type", "retry-after")


class _PerMinute:
    """A sliding window of the last minute; the service is one process, so memory is enough."""

    def __init__(self, limit: int, clock: Callable[[], float]) -> None:
        self._limit = limit
        self._clock = clock
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        now = self._clock()
        while self._hits and self._hits[0] <= now - 60:
            self._hits.popleft()
        if len(self._hits) >= self._limit:
            return False
        self._hits.append(now)
        return True


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(
    key: SigningKey,
    upstream: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> Starlette:
    """``upstream`` is the CRM's gateway root, e.g. ``http://api:8000/api/v1/agent-gateway``."""
    base = upstream.rstrip("/")
    http = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_S, follow_redirects=False, transport=transport)
    limiter = _PerMinute(PER_MINUTE, clock)
    # httpx logs every request URL at INFO, and the URL carries the person's id: only its warnings
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def token(scope: str) -> str:
        issued = int(clock())
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": issued,
            "exp": issued + TOKEN_TTL_S,
            "jti": uuid4().hex,
            "scope": scope,
        }
        return jwt.encode(claims, key.private, algorithm=ALGORITHM, headers={"kid": key.kid})

    async def body_of(request: Request) -> bytes | None:
        """The body, or ``None`` when it is longer than ``MAX_BODY``."""
        size = 0
        chunks: list[bytes] = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY:
                return None
            chunks.append(chunk)
        return b"".join(chunks)

    async def forward(request: Request) -> Response:
        started = time.monotonic()
        found = match(request.method, "/" + request.path_params["rest"])
        if found is None or len(request.url.query) > MAX_QUERY:
            return _error(404, "not_found", "Không có đường này.")
        route, path = found

        def done(response: Response) -> Response:
            log.info(
                "%s %s -> %s %dms",
                route.method,
                route.template,
                response.status_code,
                (time.monotonic() - started) * 1000,
            )
            return response

        if not limiter.allow():
            return done(_error(429, "rate_limited", "Agent gọi quá nhiều; thử lại sau ít phút."))
        body = await body_of(request)
        if body is None:
            return done(_error(413, "too_large", "Yêu cầu quá lớn."))
        headers = {name: value for name in FORWARD_IN if (value := request.headers.get(name))}
        headers["Authorization"] = f"Bearer {token(route.scope)}"
        url = httpx.URL(f"{base}{path}", query=request.url.query.encode() or None)
        try:
            answer = await http.request(route.method, url, content=body or None, headers=headers)
        except httpx.HTTPError as err:
            log.warning("upstream failed on %s %s: %s", route.method, route.template, type(err).__name__)
            return done(_error(502, "upstream_unavailable", "CRM không trả lời."))
        back = {name: answer.headers[name] for name in FORWARD_BACK if name in answer.headers}
        return done(Response(answer.content, status_code=answer.status_code, headers=back))

    async def health(_request: Request) -> Response:
        return JSONResponse({"ok": True})

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            await http.aclose()

    return Starlette(
        routes=[
            Route("/health", health),
            Route(
                PREFIX + "/{rest:path}",
                forward,
                methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            ),
        ],
        lifespan=lifespan,
    )

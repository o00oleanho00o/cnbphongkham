# ported from: src/server/routes/kb-route-guards.ts
"""Guards shared by the knowledge-base routes (``routers/admin_kb.py``): body size ceilings, the real file
signature, and the request context (who is calling, which clinic, which permissions).

Forced deviations:
* Hono ``bodyLimit`` middleware -> ``KbBodyLimitRoute``, a custom ``APIRoute``: it reads the body itself, cuts
  it AT THE READING LAYER the moment the ceiling is crossed (also when there is no ``Content-Length``) and
  only then hands a replayable body to FastAPI. FastAPI parses the body BEFORE any dependency runs and turns
  any error raised while reading it into a generic 400, so neither a dependency nor an exception raised from
  inside the receive channel could do this job. The ceiling is read again at every request
  (``KB_MAX_FILE_MB``): changing it on the dashboard takes effect at once;
* the Zod schemas (``tenNguonSchema``, ``textSourceSchema``, ``putAgentSourcesSchema``,
  ``putSourceAgentsSchema``, ``chunksQuerySchema``) are the pydantic DTOs of ``pema_contracts`` plus the
  checks
  of ``postgres_knowledge_store`` (name length, 500 ids x 64 characters, 200 agents) - the contract DTOs
  cannot carry the original's list bounds without a contract change, so the store enforces them;
* new: ``KbRequestContext`` / ``cap_quyen`` - the original had one dashboard password and no tenants. The
  context is read from ``request.state`` where the authentication of package B1 puts it (see
  ``lay_ngu_canh_kb``); a request with no such context is refused (deny by default).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Coroutine
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from fastapi import Request, Response
from fastapi.routing import APIRoute

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.knowledge.chu_ky_file import MAGIC_BYTES, khop_chu_ky_that
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

__all__ = [
    "MAGIC_BYTES",
    "TRAN_BODY_GAN_NGUON_KB",
    "KbBodyLimitRoute",
    "KbRequestContext",
    "cap_quyen",
    "gioi_han_body",
    "khop_chu_ky_that",
    "lay_ngu_canh_kb",
    "lay_store",
]

TRAN_BODY_GAN_NGUON_KB: Final = 256
"""Own body ceiling (KB) of the binding routes ``PUT .../sources`` and ``PUT .../agents``: they receive only
a list of ids, NOT document content, so they must not share the file ceiling (``KB_MAX_FILE_MB``, 20-100 MB).

The largest VALID payload is 500 ids x 64 characters plus JSON quotes/commas, about 36 KB. Sharing the file
ceiling would leave a hole about 3000 times too wide: a signed-in person could still make the server gather
tens of MB into memory before validation can refuse. 256 KB is about 7x the largest valid payload. A hard
constant, NOT on the dashboard: it is the arithmetic consequence of the two list bounds, not something an
operator has a reason to change - changing it only widens the hole."""

TRAN_BODY_NHO_KB: Final = 64
"""Ceiling (KB) for the small JSON bodies (approval, search, reindex): a few hundred bytes are valid."""


@dataclass(frozen=True, slots=True)
class GioiHanBody:
    max_bytes: int
    thong_bao: str


def gioi_han_body(method: str, path_template: str) -> GioiHanBody | None:
    """The body ceiling of a route, or ``None`` when the route takes no body. Read at EVERY request."""
    if method in ("GET", "DELETE", "HEAD", "OPTIONS"):
        return None
    if method == "POST" and path_template.endswith(("/sources/text", "/sources/file")):
        # ``c.req.json()`` / ``parseBody()`` gather the whole body into memory BEFORE anything can be
        # checked, so the cut must happen at the reading layer, for the upload and for the typed text alike.
        max_mb = get_tuning_int("KB_MAX_FILE_MB")
        return GioiHanBody(max_mb * 1024 * 1024, f"Nội dung vượt quá {max_mb}MB")
    if method == "PUT":
        return GioiHanBody(TRAN_BODY_GAN_NGUON_KB * 1024, f"Danh sách vượt quá {TRAN_BODY_GAN_NGUON_KB}KB")
    return GioiHanBody(TRAN_BODY_NHO_KB * 1024, f"Nội dung vượt quá {TRAN_BODY_NHO_KB}KB")


class KbBodyLimitRoute(APIRoute):
    """Cut an over-ceiling body at the reading layer, before FastAPI parses it (see the module docstring)."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            # Authenticate BEFORE reading or validating anything: an anonymous caller gets 401 (not a 422 that
            # describes the body schema) and can never make the server gather a large body into memory.
            lay_ngu_canh_kb(request)
            gioi_han = gioi_han_body(request.method, self.path)
            if gioi_han is None:
                return await original(request)

            khai_bao = request.headers.get("content-length")
            if khai_bao is not None and khai_bao.isdigit() and int(khai_bao) > gioi_han.max_bytes:
                raise DomainError(ErrorCode.PAYLOAD_TOO_LARGE, gioi_han.thong_bao)

            manh: list[bytes] = []
            tong = 0
            async for chunk in request.stream():
                tong += len(chunk)
                if tong > gioi_han.max_bytes:
                    raise DomainError(ErrorCode.PAYLOAD_TOO_LARGE, gioi_han.thong_bao)
                manh.append(chunk)
            body = b"".join(manh)

            async def phat_lai() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

            return await original(Request(request.scope, phat_lai))  # type: ignore[arg-type]

        return handler


@dataclass(frozen=True, slots=True)
class KbRequestContext:
    clinic_id: UUID
    user_id: UUID
    role: str
    permissions: frozenset[str]


def lay_ngu_canh_kb(request: Request) -> KbRequestContext:
    """Who is calling. Read from ``request.state``, where the session authentication of package B1 must put
    ``clinic_id`` (UUID), ``user_id`` (UUID), ``role`` (str) and ``permissions`` (collection of permission
    codes) BEFORE the route runs. Missing context = not authenticated (deny by default), never a default
    clinic."""
    state = request.state
    clinic_id = getattr(state, "clinic_id", None)
    user_id = getattr(state, "user_id", None)
    role = getattr(state, "role", None)
    permissions: Collection[str] | None = getattr(state, "permissions", None)
    if (
        not isinstance(clinic_id, UUID)
        or not isinstance(user_id, UUID)
        or not isinstance(role, str)
        or permissions is None
    ):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập.")
    return KbRequestContext(
        clinic_id=clinic_id, user_id=user_id, role=role, permissions=frozenset(str(p) for p in permissions)
    )


def cap_quyen(ctx: KbRequestContext, permission: Permission) -> None:
    """Refuse unless the caller holds ``permission`` (deny by default)."""
    if permission.value not in ctx.permissions:
        raise DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.")


def lay_store(request: Request) -> PostgresKnowledgeStore:
    """The knowledge store of the application, put on ``app.state.knowledge_store`` by the composition
    root."""
    store = getattr(request.app.state, "knowledge_store", None)
    if not isinstance(store, PostgresKnowledgeStore):
        raise DomainError(ErrorCode.INTERNAL, "Kho tri thức chưa được khởi tạo.")
    return store

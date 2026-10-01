# ported from: src/server/routes/mcp-route-guards.ts
"""Guards for ``/admin/mcp`` (``routers/admin_mcp.py``). Kept apart so the route file stays short, for the
same
reason ``kb-route-guards.ts`` was split from ``kb-routes.ts``.

Forced deviation (zod -> pydantic): the shape checks the original did with zod are split. What the contract
DTOs (``McpServerCreate``, ``McpServerUpdate``, ``IdList``) already enforce is not repeated: the name length
(the contract allows 100, stricter than the original 200), an ``http(s)://`` prefix, the types. What the DTOs
cannot express (a contract change belongs to package G) is checked here and raises
``DomainError(VALIDATION_FAILED)``:

* "ten" is shown on the dashboard BUT also goes straight into the tool label sent to the LLM (``"<server
  name>: <tool name>"``) and into the untrusted-content wrapper label, so it is bounded at the edge instead of
  letting a huge string into the tool schema of every turn that uses the server (the name is limited by the
  DTO, ``max_length=100``);
* the URL: at most 2048 characters, an ``http``/``https`` scheme and a host (zod ``.url()``);
* the headers (an authentication header such as ``Authorization``): an admin types them, not a stranger, but
  they are still capped (name 200, value 4000) so a huge value does not end up encrypted and stored for ever,
  and header names must be valid HTTP tokens and values must not contain CR, LF or NUL (header injection: new,
  not in the original, which let the HTTP client library refuse them);
* the id lists: server id 16 hex characters or an agent id of a few dozen, ``max 64`` per element, plus a
  total ceiling (500 servers per agent, 200 agents per server), mirroring ``putAgentSourcesSchema`` /
  ``putSourceAgentsSchema``: without an element ceiling the total ceiling would not stop ONE huge element from
  eating RAM before anything is checked.

New (no equivalent in the original, which mounted the Hono app behind ``dashboard-auth``): ``McpAdminContext``
and ``get_mcp_admin_context``, the dependency that gives a route the clinic of the session, the stores and the
manager. The default raises ``not_implemented`` (501, like the rest of the skeleton): package G overrides it
(``app.dependency_overrides`` or by replacing the function) with B1's session check for the ``admin.mcp``
permission, so a route can never run without that check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Annotated, Final, NoReturn, Protocol
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Depends

from pema.api.deps import not_implemented
from pema.mcp.mcp_agent_binding import McpBindingStore
from pema.mcp.mcp_server_store import McpServerStore
from pema_contracts.admin_agent import McpServerCreate, McpServerUpdate
from pema_contracts.errors import DomainError, ErrorCode

MAX_URL_LENGTH: Final = 2048
MAX_HEADER_NAME_LENGTH: Final = 200
MAX_HEADER_VALUE_LENGTH: Final = 4000
MAX_ID_LENGTH: Final = 64
MAX_SERVER_IDS: Final = 500
MAX_AGENT_IDS: Final = 200

_HEADER_NAME_RE: Final = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_FORBIDDEN_VALUE_CHARS: Final = ("\r", "\n", "\x00")


def _invalid(message: str) -> NoReturn:
    raise DomainError(ErrorCode.VALIDATION_FAILED, message)


def check_server_url(url: str) -> None:
    if len(url) > MAX_URL_LENGTH:
        _invalid(f"URL máy chủ MCP dài tối đa {MAX_URL_LENGTH} ký tự.")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        _invalid("URL máy chủ MCP không hợp lệ.")
    if parts.scheme not in {"http", "https"} or not host or any(c.isspace() for c in url):
        _invalid("URL máy chủ MCP không hợp lệ.")


def check_headers(headers: dict[str, str] | None) -> None:
    for name, value in (headers or {}).items():
        if not name or len(name) > MAX_HEADER_NAME_LENGTH or not _HEADER_NAME_RE.fullmatch(name):
            _invalid("Tên header không hợp lệ.")
        if len(value) > MAX_HEADER_VALUE_LENGTH or any(c in value for c in _FORBIDDEN_VALUE_CHARS):
            _invalid("Giá trị header không hợp lệ.")


def check_create(body: McpServerCreate) -> None:
    check_server_url(body.url)
    check_headers(body.headers)


def check_update(body: McpServerUpdate) -> None:
    if body.url is not None:
        check_server_url(body.url)
    check_headers(body.headers)


def _check_ids(ids: list[str], *, max_items: int, what: str) -> None:
    if len(ids) > max_items:
        _invalid(f"Tối đa {max_items} {what}.")
    if any(len(i) > MAX_ID_LENGTH or not i for i in ids):
        _invalid(f"Mã {what} không hợp lệ.")


def check_server_ids(ids: list[str]) -> None:
    """``ganServerSchema``: ``serverIds`` of ``PUT /agents/{id}/servers``."""
    _check_ids(ids, max_items=MAX_SERVER_IDS, what="máy chủ MCP")


def check_agent_ids(ids: list[str]) -> None:
    """``ganAgentSchema``: ``agentIds`` of ``PUT /servers/{id}/agents``."""
    _check_ids(ids, max_items=MAX_AGENT_IDS, what="agent")


class McpAdminManager(Protocol):
    """The part of the manager the routes use (``DefaultMcpManager`` implements it; the original injected
    ``manager`` through ``deps`` so tests need no real network)."""

    async def reconnect_server(self, clinic_id: UUID, server_id: str) -> None: ...

    async def disconnect_server(self, clinic_id: UUID, server_id: str) -> None: ...

    async def reapprove_drift(self, clinic_id: UUID, server_id: str) -> None: ...

    async def refresh_bindings(self, clinic_id: UUID) -> None: ...


@dataclass(frozen=True)
class McpAdminContext:
    clinic_id: UUID
    servers: McpServerStore
    bindings: McpBindingStore
    manager: McpAdminManager


async def get_mcp_admin_context() -> McpAdminContext:
    """Default: not wired yet (501). Replace it with the dependency that checks the session and the
    ``admin.mcp`` permission and builds the context (package G with B1's auth)."""
    not_implemented()


McpAdmin = Annotated[McpAdminContext, Depends(get_mcp_admin_context)]

"""The agent's machine key: the one way into ``/agent-gateway`` (docs/PLAN-crm-plugin.md, rule L2).

New module. ``Authorization: Bearer <key>``; the API keeps only the SHA-256 of the key
(``PEMA_AGENT_GATEWAY_KEY_SHA256``) and compares in constant time. The key opens the gateway's routes and
nothing else: every other router depends on the session cookie, and these depend on this key only, so a
staff cookie gets 401 here and the key gets 401 there. With no hash set the gateway is off (404).

Budgets (in-process, like the login limiter): ``ALL_PER_MINUTE`` calls for the whole key and
``WRITES_PER_HOUR`` writes per chat person.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pema.api.read_rate_limit import FixedWindowLimiter
from pema.api.request_id import clean_request_id
from pema.config.env import get_settings
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType

ALL_PER_MINUTE = 300
WRITES_PER_HOUR = 10

agent_gateway_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AgentGatewayKey",
    description="The agent service's machine key (only /agent-gateway accepts it).",
)

_all_calls = FixedWindowLimiter(max_hits=ALL_PER_MINUTE)
_person_writes = FixedWindowLimiter(max_hits=WRITES_PER_HOUR, window_ms=3_600_000)


def reset_agent_gateway_limits() -> None:
    _all_calls.reset()
    _person_writes.reset()


def _expected_hash() -> str | None:
    secret = get_settings().agent_gateway_key_sha256
    value = secret.get_secret_value().strip().lower() if secret is not None else ""
    return value or None


def agent_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(agent_gateway_scheme)],
) -> ActionContext:
    expected = _expected_hash()
    if expected is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy.")
    given = hashlib.sha256(credentials.credentials.encode()).hexdigest() if credentials else ""
    if not hmac.compare_digest(given, expected):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Khóa của agent không hợp lệ.")
    if not _all_calls.allow("all"):
        raise DomainError(ErrorCode.RATE_LIMITED, "Agent gọi quá nhiều; thử lại sau ít phút.")
    return ActionContext(
        actor_type=ActorType.AGENT,
        source=ActionSource.AGENT,
        request_id=clean_request_id(request.headers.get("x-request-id")),
        idempotency_key=(request.headers.get("idempotency-key") or None),
    )


AgentCtx = Annotated[ActionContext, Depends(agent_context)]


def count_person_write(channel: str, external_id: str) -> None:
    """One write for this chat person; past the hour's budget the call is refused."""
    if not _person_writes.allow(f"{channel}\x00{external_id}"):
        raise DomainError(ErrorCode.RATE_LIMITED, "Người này đã thay đổi quá nhiều lần trong một giờ.")

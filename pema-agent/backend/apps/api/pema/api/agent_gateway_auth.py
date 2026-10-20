"""Who may call ``/agent-gateway``: a short-lived token signed by ``crm-signer`` (PLAN-crm-plugin.md 3.2, L2).

New module. ``Authorization: Bearer <JWT>``, EdDSA, signed with the private key only ``crm-signer`` holds; the
API keeps the public keys (``PEMA_AGENT_GATEWAY_PUBLIC_KEYS``: one, or two while a key is being changed), so
nothing the API or the agent's process holds can sign a call. A token is accepted when:

* its signature is one of the public keys and its algorithm is EdDSA;
* ``iss`` is ``pema-crm-signer`` and ``aud`` is ``pema-agent-gateway`` (the SSO token of the agent,
  ``aud = pema-agent``, never passes);
* it carries ``iat``, ``exp`` and ``jti``, lives at most ``MAX_LIFETIME_S`` and has not expired;
* its ``jti`` was not used before (kept in memory until the token expires);
* its ``scope`` (space separated) holds the permission of the route.

The token opens the gateway's routes and nothing else: every other router depends on the session cookie, these
on this token only. With no public key set the gateway is off (404).

Budgets (in-process, like the login limiter): ``ALL_PER_MINUTE`` calls for the gateway and ``WRITES_PER_HOUR``
writes per chat person.
"""

from __future__ import annotations

import base64
import time
from functools import lru_cache
from typing import Annotated, Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pema.api.read_rate_limit import FixedWindowLimiter
from pema.api.request_id import clean_request_id
from pema.config.env import get_settings
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission

ISSUER = "pema-crm-signer"
AUDIENCE = "pema-agent-gateway"
ALGORITHM = "EdDSA"
MAX_LIFETIME_S = 120
LEEWAY_S = 10
ALL_PER_MINUTE = 300
WRITES_PER_HOUR = 10
SEEN_PRUNE_AT = 5_000

agent_gateway_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AgentGatewayToken",
    description="A JWT that crm-signer signs for one call (only /agent-gateway accepts it).",
)

_all_calls = FixedWindowLimiter(max_hits=ALL_PER_MINUTE)
_person_writes = FixedWindowLimiter(max_hits=WRITES_PER_HOUR, window_ms=3_600_000)
_seen: dict[str, float] = {}
"""``jti`` -> expiry of the tokens already used."""


def reset_agent_gateway_limits() -> None:
    _all_calls.reset()
    _person_writes.reset()
    _seen.clear()


@lru_cache(maxsize=4)
def _public_keys(raw: str) -> tuple[Ed25519PublicKey, ...]:
    """Comma separated keys, each the 32 raw bytes in base64url (the ``x`` of a JWK). A wrong value raises."""
    keys: list[Ed25519PublicKey] = []
    for part in (p.strip() for p in raw.split(",")):
        if part:
            keys.append(
                Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            )
    return tuple(keys)


def _configured_keys() -> tuple[Ed25519PublicKey, ...]:
    raw = get_settings().agent_gateway_public_keys
    return _public_keys(raw.strip()) if raw and raw.strip() else ()


def _verified(token: str, keys: tuple[Ed25519PublicKey, ...]) -> dict[str, Any] | None:
    for key in keys:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=LEEWAY_S,
                options={"require": ["exp", "iat", "jti", "iss", "aud"]},
            )
        except jwt.InvalidSignatureError:
            continue  # the other key, while a key is being changed
        except jwt.PyJWTError:
            return None
    return None


def _first_use(jti: str, expires: float) -> bool:
    now = time.time()
    if len(_seen) > SEEN_PRUNE_AT:
        for old in [k for k, exp in _seen.items() if exp < now]:
            del _seen[old]
    if _seen.get(jti, 0.0) >= now:
        return False
    _seen[jti] = expires + LEEWAY_S
    return True


def _unauthenticated() -> DomainError:
    return DomainError(ErrorCode.UNAUTHENTICATED, "Token của agent không hợp lệ.")


def agent_gateway(permission: Permission) -> Any:
    """``Depends`` of a gateway route: the caller is the agent, with ``permission`` in its token's scope."""

    def context(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Security(agent_gateway_scheme)],
    ) -> ActionContext:
        keys = _configured_keys()
        if not keys:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy.")
        claims = _verified(credentials.credentials, keys) if credentials else None
        if claims is None:
            raise _unauthenticated()
        issued, expires = float(claims["iat"]), float(claims["exp"])
        if expires - issued > MAX_LIFETIME_S or not _first_use(str(claims["jti"]), expires):
            raise _unauthenticated()
        if permission.value not in str(claims.get("scope", "")).split():
            raise DomainError(
                ErrorCode.FORBIDDEN,
                "Token của agent không có quyền này.",
                details={"permission": permission.value},
            )
        if not _all_calls.allow("all"):
            raise DomainError(ErrorCode.RATE_LIMITED, "Agent gọi quá nhiều; thử lại sau ít phút.")
        return ActionContext(
            actor_type=ActorType.AGENT,
            source=ActionSource.AGENT,
            request_id=clean_request_id(request.headers.get("x-request-id")),
            idempotency_key=(request.headers.get("idempotency-key") or None),
        )

    return Depends(context)


def count_person_write(channel: str, external_id: str) -> None:
    """One write for this chat person; past the hour's budget the call is refused."""
    if not _person_writes.allow(f"{channel}\x00{external_id}"):
        raise DomainError(ErrorCode.RATE_LIMITED, "Người này đã thay đổi quá nhiều lần trong một giờ.")

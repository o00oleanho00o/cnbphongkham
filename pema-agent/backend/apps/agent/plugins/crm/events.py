"""``POST /v1/hooks/crm/events``: the CRM tells the agent what changed (docs/PLAN-crm-plugin.md 3.4).

The CRM sends one event per call as a JWT in ``Authorization: Bearer``, signed with the key whose public half
it publishes (the JWKS the ``sso`` plugin also reads): ``iss`` pema-clinic, ``aud`` pema-agent-events, at most
two minutes, ``jti`` the event id, the event in the claim ``event``. Only that audience is taken here, and the
``sso`` plugin takes only its own, so an event never opens a session and a session token is never an event.

The route writes STATE into the store (``store.py``) and answers at once: no model call, no CRM call, nothing
returned to the CRM but ``{"ok": true}``. An event kind it does not know is accepted and ignored, so a newer
CRM does not make the older agent's outbox retry for nothing. This is a trigger of the owner's loop frame
(docs/IDEAS-agent-loops.md 5): once an event is applied, ``on_change`` gets the visit as it was before it
(None for a new visit or an event about a person), and wakes the reminder cases of that visit.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Final, Literal
from uuid import UUID

import jwt
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from plugin_kit import KeySet, KeysUnavailableError

from .store import ReminderStore, Visit

ISSUER: Final = "pema-clinic"
AUDIENCE: Final = "pema-agent-events"
MAX_LIFETIME_S: Final = 120
LEEWAY_S: Final = 30

logger = logging.getLogger(__name__)


class AppointmentChanged(BaseModel):
    kind: Literal["appointment.changed"]
    appointment_id: UUID
    channel: str
    external_id: str
    starts_at: datetime
    duration_min: int
    status: str
    version: int
    messages_consent: bool | None = None
    actor_type: str
    occurred_at: datetime


class PersonChanged(BaseModel):
    kind: Literal["person.changed"]
    channel: str
    external_id: str
    messages_consent: bool | None = None
    actor_type: str
    occurred_at: datetime


class EventVerifier:
    def __init__(self, keys: KeySet) -> None:
        self._keys = keys

    async def claims(self, token: str) -> dict[str, Any] | None:
        """The verified claims, or None for anything that is not a fresh event token of the CRM. Raises
        ``KeysUnavailableError`` when the CRM's keys cannot be fetched (the CRM then tries again later)."""
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError:
            return None
        if not isinstance(kid, str):
            return None
        key = await self._keys.key(kid)
        if key is None or key.algorithm_name != "EdDSA":
            return None
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["EdDSA"],
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=LEEWAY_S,
                options={"require": ["iss", "aud", "exp", "iat", "jti"]},
            )
        except jwt.PyJWTError:
            return None
        if float(claims["exp"]) - float(claims["iat"]) > MAX_LIFETIME_S:
            return None
        return claims


def _answer(status: int, code: str) -> JSONResponse:
    return JSONResponse({"ok": status == 200, "code": code}, status_code=status)


async def apply(store: ReminderStore, event_id: UUID, event: dict[str, Any]) -> bool:
    """Writes the event into ``store``. True when it was a known kind; raises ``ValidationError`` on a known
    kind that is malformed."""
    kind = event.get("kind")
    if kind == "appointment.changed":
        e = AppointmentChanged.model_validate(event)
        await store.apply_visit(
            Visit(
                appointment_id=e.appointment_id,
                channel=e.channel,
                external_id=e.external_id,
                starts_at=e.starts_at,
                duration_min=e.duration_min,
                status=e.status,
                version=e.version,
                changed_at=e.occurred_at,
                actor_type=e.actor_type,
                last_event_id=event_id,
            )
        )
        await store.apply_consent(e.channel, e.external_id, e.messages_consent, e.occurred_at)
        return True
    if kind == "person.changed":
        p = PersonChanged.model_validate(event)
        await store.apply_consent(p.channel, p.external_id, p.messages_consent, p.occurred_at)
        return True
    return False


async def _nothing(before: Visit | None) -> None:
    return None


async def _before(store: ReminderStore, event: dict[str, Any]) -> Visit | None:
    """The visit an ``appointment.changed`` event is about, as held before it; ``ValueError`` on a bad id."""
    if event.get("kind") != "appointment.changed":
        return None
    return await store.visit(UUID(str(event.get("appointment_id"))))


def events_router(
    verifier: EventVerifier,
    store: ReminderStore,
    on_change: Callable[[Visit | None], Awaitable[None]] = _nothing,
) -> APIRouter:
    """``on_change(before)`` runs after an event was applied: it wakes the reminders."""
    router = APIRouter()

    @router.post("/events")
    async def receive(authorization: Annotated[str | None, Header()] = None) -> JSONResponse:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if not token:
            return _answer(401, "unauthenticated")
        try:
            claims = await verifier.claims(token)
        except KeysUnavailableError:
            return _answer(503, "keys_unavailable")
        if claims is None:
            return _answer(401, "unauthenticated")
        event: Any = claims.get("event")
        body: dict[str, Any] = event if isinstance(event, dict) else {}  # pyright: ignore[reportUnknownVariableType]
        try:
            event_id = UUID(str(claims["jti"]))
            before = await _before(store, body)
            known = await apply(store, event_id, body)
        except (ValueError, ValidationError):
            logger.warning("a CRM event could not be read (jti %s)", claims.get("jti"))
            return _answer(422, "malformed_event")
        if known:
            await on_change(before)
        return _answer(200, "applied" if known else "ignored")

    return router

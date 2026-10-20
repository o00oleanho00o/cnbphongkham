"""Sends the outbox ``clinic.agent_event`` to the agent (docs/PLAN-crm-plugin.md 3.4). New module.

One worker in the API process. It sleeps until a commit that wrote events wakes it
(``agent_events.set_waker``) or until the next retry is due; it never scans on a timer. It takes the due
rows in the order of ``id`` and, for each, signs a JWT with the key the clinic already signs the agent's SSO
tokens with (``iss`` pema-clinic, ``aud`` pema-agent-events, ``jti`` the event id, 2 minutes, the event in the
claim ``event``) and POSTs it as ``Authorization: Bearer`` to ``PEMA_AGENT_EVENTS_URL``. The agent holds only
the public key, so nothing it holds can forge an event, and its SSO check refuses this audience.

A 2xx marks the row delivered. Anything else is a failed try: ``attempts`` +1 and the next try after
``RETRY_BASE_S`` * 2^(attempts-1) seconds (at most ``RETRY_CAP_S``); after ``MAX_ATTEMPTS`` the row is marked
failed and left (the agent reconciles from the CRM on its own schedule). A refused or timed-out connection
ends the round at once: the agent is down, the other rows can wait. No call holds a database transaction,
and no error leaves the loop. Delivered rows are deleted after ``KEEP_DELIVERED_DAYS``, failed ones after
``KEEP_FAILED_DAYS``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

import httpx
import jwt
from sqlalchemy import delete, func, select, update

from pema.api import agent_token
from pema.clinic.models.agent_event import AgentEvent
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger

log = create_logger("composition.agent_events")

AUDIENCE: Final = "pema-agent-events"
TOKEN_TTL_S: Final = 120
SEND_TIMEOUT_S: Final = 5.0
BATCH: Final = 50
MAX_ATTEMPTS: Final = 8
RETRY_BASE_S: Final = 30
RETRY_CAP_S: Final = 3600
MIN_ROUND_GAP_S: Final = 5.0
"""After a round with a failed try, never start the next one sooner than this."""
CRASH_PAUSE_S: Final = 30.0
KEEP_DELIVERED_DAYS: Final = 7
KEEP_FAILED_DAYS: Final = 30
CLEANUP_EVERY: Final = timedelta(hours=1)
ERROR_CHARS: Final = 200


@dataclass(frozen=True, slots=True)
class Round:
    sent: int
    failed: int
    next_due: datetime | None
    """When the soonest waiting row is due; ``None`` when nothing waits."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentEventWorker:
    def __init__(
        self,
        db: ClinicDatabase,
        url: str,
        *,
        key: Callable[[], agent_token.SigningKey] = agent_token.signing_key,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._db = db
        self._url = url.strip()
        self._key = key
        self._transport = transport
        self._clock = clock
        self._wake = asyncio.Event()
        self._last_cleanup: datetime | None = None

    def wake(self) -> None:
        """Safe from any task of the same event loop (it is called after a commit)."""
        self._wake.set()

    def _token(self, row: AgentEvent) -> str:
        signing = self._key()
        issued = int(self._clock().timestamp())
        claims = {
            "iss": agent_token.ISSUER,
            "aud": AUDIENCE,
            "iat": issued,
            "exp": issued + TOKEN_TTL_S,
            "jti": str(row.event_id),
            "event": {"kind": row.kind, **row.payload},
        }
        return jwt.encode(
            claims, signing.private, algorithm=agent_token.ALGORITHM, headers={"kid": signing.kid}
        )

    async def _due(self) -> list[AgentEvent]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(AgentEvent)
                .where(
                    AgentEvent.delivered_at.is_(None),
                    AgentEvent.failed_at.is_(None),
                    AgentEvent.next_attempt_at <= self._clock(),
                )
                .order_by(AgentEvent.id)
                .limit(BATCH)
            )
            found = list(rows)
            session.expunge_all()
            return found

    async def _next_due(self) -> datetime | None:
        async with self._db.session() as session:
            return await session.scalar(
                select(func.min(AgentEvent.next_attempt_at)).where(
                    AgentEvent.delivered_at.is_(None), AgentEvent.failed_at.is_(None)
                )
            )

    async def _mark_delivered(self, row: AgentEvent) -> None:
        async with self._db.session() as session:
            await session.execute(
                update(AgentEvent)
                .where(AgentEvent.id == row.id)
                .values(delivered_at=self._clock(), attempts=row.attempts + 1, last_error=None)
            )

    async def _mark_failed_try(self, row: AgentEvent, reason: str) -> None:
        attempts = row.attempts + 1
        at = self._clock()
        values: dict[str, object] = {"attempts": attempts, "last_error": reason[:ERROR_CHARS]}
        if attempts >= MAX_ATTEMPTS:
            values["failed_at"] = at
        else:
            delay = min(RETRY_BASE_S * 2 ** (attempts - 1), RETRY_CAP_S)
            values["next_attempt_at"] = at + timedelta(seconds=delay)
        async with self._db.session() as session:
            await session.execute(update(AgentEvent).where(AgentEvent.id == row.id).values(**values))

    async def deliver_due(self, http: httpx.AsyncClient) -> Round:
        sent = failed = 0
        for row in await self._due():
            try:
                response = await http.post(self._url, headers={"Authorization": f"Bearer {self._token(row)}"})
            except httpx.TransportError as err:
                await self._mark_failed_try(row, f"{type(err).__name__}")
                failed += 1
                break  # the agent is not reachable: the rest waits for its own turn
            if response.is_success:
                await self._mark_delivered(row)
                sent += 1
            else:
                await self._mark_failed_try(row, f"HTTP {response.status_code}")
                failed += 1
        return Round(sent, failed, await self._next_due())

    async def cleanup(self) -> None:
        at = self._clock()
        async with self._db.session() as session:
            await session.execute(
                delete(AgentEvent).where(AgentEvent.delivered_at < at - timedelta(days=KEEP_DELIVERED_DAYS))
            )
            await session.execute(
                delete(AgentEvent).where(AgentEvent.failed_at < at - timedelta(days=KEEP_FAILED_DAYS))
            )
        self._last_cleanup = at

    async def _cleanup_if_due(self) -> None:
        if self._last_cleanup is None or self._clock() - self._last_cleanup >= CLEANUP_EVERY:
            await self.cleanup()

    async def run(self) -> None:
        async with httpx.AsyncClient(
            timeout=SEND_TIMEOUT_S, follow_redirects=False, transport=self._transport
        ) as http:
            while True:
                # a wake that comes while a round runs stays set, so the next round starts at once
                self._wake.clear()
                wait: float | None = None
                try:
                    await self._cleanup_if_due()
                    done = await self.deliver_due(http)
                    if done.sent or done.failed:
                        log.info("agent events", sent=done.sent, failed=done.failed)
                    if done.next_due is not None:
                        wait = max(0.0, (done.next_due - self._clock()).total_seconds())
                    if done.failed:
                        wait = max(wait or 0.0, MIN_ROUND_GAP_S)
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # the loop outlives any error of one round
                    log.error("agent events round failed", err=err)
                    wait = CRASH_PAUSE_S
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=wait)

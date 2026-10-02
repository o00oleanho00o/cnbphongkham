"""The body of ``GET /api/v1/events``: server-sent events for one signed-in staff member (ST-R).

New module (not a port). Format: the default ``message`` event, ``data`` = the JSON of a ``LiveEvent``
(the two keys ``type`` and ``id``, see ``bus.encode_event``), a ``retry:`` line first, and a comment line
(``: keep-alive``) every ``KEEPALIVE_S`` seconds so proxies and the browser see the connection is alive.

The stream is re-authorised every ``RECHECK_S`` seconds by ``refresh_access`` (the caller verifies the cookie
token again): a logout, an expired session (sliding or absolute) or a deactivated account ends the stream, a
role change takes effect on the next check. The set of event types a person receives follows their
permissions, and a doctor (who sees only the conversations of their own patients) receives no ids at all.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from pema.live.bus import encode_event
from pema.live.hub import LiveHub, Subscription
from pema_contracts.live import LiveEvent, LiveEventType

KEEPALIVE_S = 15.0
RECHECK_S = 15.0
RETRY_MS = 3000
KEEPALIVE_FRAME = ": keep-alive\n\n"

RESPONSE_HEADERS: dict[str, str] = {
    # no-transform: a compressing proxy (Next.js, Caddy) must not hold the stream back to fill a gzip block
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True)
class StreamAccess:
    """What one person may receive: the event types, and whether ids go with them."""

    types: frozenset[LiveEventType]
    with_ids: bool


def frame(event: LiveEvent) -> str:
    return f"data: {encode_event(event)}\n\n"


def _visible(event: LiveEvent, access: StreamAccess) -> LiveEvent | None:
    if event.type not in access.types:
        return None
    return event if access.with_ids else LiveEvent(type=event.type, id=None)


async def event_stream(
    hub: LiveHub,
    sub: Subscription,
    *,
    access: StreamAccess,
    refresh_access: Callable[[], Awaitable[StreamAccess | None]],
    keepalive_s: float | None = None,
    recheck_s: float | None = None,
) -> AsyncIterator[str]:
    """Yields the SSE frames until the session ends, the bus is lost or the client goes away (the generator
    is then cancelled; ``finally`` releases the subscription either way). ``refresh_access`` returns the
    current access, or ``None`` when the session is over."""
    keepalive = KEEPALIVE_S if keepalive_s is None else keepalive_s
    recheck = RECHECK_S if recheck_s is None else recheck_s
    current = access
    last_check = time.monotonic()
    try:
        yield f"retry: {RETRY_MS}\n\n"
        while not sub.closed:
            batch = await sub.next_batch(keepalive)
            if sub.closed:
                return
            if time.monotonic() - last_check >= recheck * 0.9:
                last_check = time.monotonic()
                refreshed = await refresh_access()
                if refreshed is None:
                    return
                current = refreshed
            sent = False
            for event in batch:
                visible = _visible(event, current)
                if visible is not None:
                    sent = True
                    yield frame(visible)
            if not sent:
                yield KEEPALIVE_FRAME
    finally:
        hub.unsubscribe(sub)

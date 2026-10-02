"""Live updates: ``GET /api/v1/events`` (server-sent events) for the signed-in staff member (package ST-R).

New router, no zalo-agent source. The stream tells the screens WHAT changed ("inbox.changed", "tasks.changed",
"review.changed", "presence.changed", each with the id of the object or null) and never the content: no
message
text, no name, no phone. The screens refetch through the normal API, so authorization stays where it is.

Security (SECURITY-REVIEW-AI01 SEC-49 to SEC-52): a valid staff session is required (the middleware refuses a
call with no cookie, ``current_user`` verifies it); the stream is re-authorised every 15 seconds and ends with
the session (logout, expiry, deactivation); at most 5 streams per person and 200 per process (429 past it);
only the event types the role may read are sent, and a doctor's stream carries no ids.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Security
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from pema.api import dashboard_auth
from pema.api.dashboard_auth import CurrentUser, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.api.live_access import LiveDep, stream_access_of
from pema.config.env import get_settings
from pema.live.hub import TooManyStreamsError
from pema.live.sse import RESPONSE_HEADERS, StreamAccess, event_stream
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.live import LiveEvent

router = APIRouter(tags=["live"], responses=ERROR_RESPONSES)
staff = [Security(cookie_scheme)]

UNAVAILABLE_MESSAGE = "Cập nhật trực tiếp tạm thời không dùng được. Màn hình sẽ tự tải lại theo chu kỳ."
TOO_MANY_MESSAGE = "Đã mở quá nhiều luồng cập nhật. Hãy đóng bớt các tab khác."
BUS_WAIT_S = 2.0


class EventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


@router.get(
    "/events",
    response_class=EventStreamResponse,
    dependencies=staff,
    summary="Live updates (server-sent events)",
    description=(
        "Each event is the default `message` event whose data is a `LiveEvent` JSON. It says that something "
        "changed, never what: refetch the list you show. A comment line every 15 seconds keeps the "
        "connection open. The stream ends when the session ends; the browser reconnects by itself. 503 "
        "while the live bus is down (the screen then polls), 429 past 5 streams per person."
    ),
    responses={200: {"model": LiveEvent, "description": "text/event-stream of LiveEvent."}},
)
async def stream_events(
    request: Request, user: CurrentUser, db: Database, live: LiveDep
) -> StreamingResponse:
    if live is None or not await live.hub.wait_available(BUS_WAIT_S):
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, UNAVAILABLE_MESSAGE)
    try:
        sub = live.hub.subscribe(user.user_id)
    except TooManyStreamsError as err:
        raise DomainError(ErrorCode.RATE_LIMITED, TOO_MANY_MESSAGE) from err

    token = request.cookies.get(get_settings().session_cookie_name)

    async def refresh_access() -> StreamAccess | None:
        try:
            fresh = await dashboard_auth.verify_session_token(db, token)
        except Exception:
            return None  # fail closed: the browser reconnects and is checked again from scratch
        return None if fresh is None else stream_access_of(fresh)

    return EventStreamResponse(
        event_stream(live.hub, sub, access=stream_access_of(user), refresh_access=refresh_access),
        headers=RESPONSE_HEADERS,
        background=BackgroundTask(live.hub.unsubscribe, sub),
    )

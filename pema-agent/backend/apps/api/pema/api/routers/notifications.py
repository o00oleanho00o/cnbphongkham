"""Notifications of the shared inbox (package O, step O3): own notices, ack, push tokens, linking the personal
Zalo, quiet hours, and the clinic's settings.

Thin routes over ``pema.clinic.actions.notification_inbox``. Everything under ``/me`` and ``/notifications``
works on the signed-in operator's own rows only (permission ``notify.self``); the settings need
``notify.manage`` (owner and manager). A push token and a linking code are never returned after creation.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import notification_inbox as inbox
from pema_contracts.ops import (
    AckedOut,
    AckTargetIn,
    NotificationOut,
    NotifyLinkOut,
    NotifyLinkStatus,
    NotifyPreferenceIn,
    NotifyPreferenceOut,
    NotifySettingsOut,
    NotifySettingsUpdate,
    PushTokenIn,
    PushTokenOut,
)

router = APIRouter(tags=["notifications"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])


@router.get(
    "/me/notifications",
    response_model=list[NotificationOut],
    summary="My notices, newest first",
    description="The in-app channel of the chain. Only the caller's own rows; the payload is PII-free.",
)
async def list_my_notifications(
    db: Database, ctx: Ctx, unacked_only: bool = False, limit: int = Query(default=50, ge=1, le=200)
) -> list[NotificationOut]:
    return await inbox.list_own(db, ctx, unacked_only=unacked_only, limit=limit)


@router.post(
    "/notifications/{notification_id}/ack",
    response_model=NotificationOut,
    summary="Acknowledge one notice",
    description=(
        "Stops the chain of that notice (no bell). Repeating it changes nothing. Somebody else's notice is a "
        "404. It does not accept a handoff: the SLA of package M keeps running."
    ),
)
async def ack_notification(notification_id: UUID, db: Database, ctx: Ctx) -> NotificationOut:
    return await inbox.ack(db, ctx, notification_id)


@router.post(
    "/notifications/ack",
    response_model=AckedOut,
    summary="Acknowledge the notices of a conversation or handoff request (deep link opened)",
)
async def ack_target(body: AckTargetIn, db: Database, ctx: Ctx) -> AckedOut:
    count = await inbox.ack_target(db, ctx, conversation_id=body.conversation_id, request_id=body.request_id)
    return AckedOut(acked=count)


@router.post(
    "/me/push-tokens",
    response_model=PushTokenOut,
    summary="Register this device for push",
    description="Stored encrypted, never returned. Registering a known token only refreshes it.",
)
async def register_push_token(body: PushTokenIn, db: Database, ctx: Ctx) -> PushTokenOut:
    return await inbox.register_push_token(db, ctx, body)


@router.delete(
    "/me/push-tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget one of my devices",
)
async def delete_push_token(token_id: UUID, db: Database, ctx: Ctx) -> Response:
    await inbox.delete_push_token(db, ctx, token_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/notify-zalo", response_model=NotifyLinkStatus, summary="Is my personal Zalo linked?")
async def notify_zalo_status(db: Database, ctx: Ctx) -> NotifyLinkStatus:
    return await inbox.link_status(db, ctx)


@router.post(
    "/me/notify-zalo/link",
    response_model=NotifyLinkOut,
    summary="Start linking my personal Zalo (one-time code)",
    description=(
        "Returns a code valid for 10 minutes. Send it as a message to the clinic's internal Zalo account; "
        "the inbound handler of that account links the sender. The code works once."
    ),
)
async def start_notify_zalo_link(db: Database, ctx: Ctx) -> NotifyLinkOut:
    return await inbox.start_link(db, ctx)


@router.delete("/me/notify-zalo", response_model=NotifyLinkStatus, summary="Unlink my personal Zalo")
async def unlink_notify_zalo(db: Database, ctx: Ctx) -> NotifyLinkStatus:
    return await inbox.unlink(db, ctx)


@router.get("/me/notify-preferences", response_model=NotifyPreferenceOut, summary="My quiet hours")
async def get_my_preferences(db: Database, ctx: Ctx) -> NotifyPreferenceOut:
    return await inbox.get_preference(db, ctx)


@router.put(
    "/me/notify-preferences",
    response_model=NotifyPreferenceOut,
    summary="Set my quiet hours",
    description="Quiet hours silence the personal Zalo bell; an urgent notice still rings.",
)
async def set_my_preferences(body: NotifyPreferenceIn, db: Database, ctx: Ctx) -> NotifyPreferenceOut:
    return await inbox.set_preference(db, ctx, body)


@router.get(
    "/notifications/settings", response_model=NotifySettingsOut, summary="Notification settings of the clinic"
)
async def get_notify_settings(db: Database, ctx: Ctx) -> NotifySettingsOut:
    return await inbox.get_settings(db, ctx)


@router.put(
    "/notifications/settings",
    response_model=NotifySettingsOut,
    summary="Change the notification settings (owner and manager)",
    description="Ack timeout, team group id, which steps are on, public base URL of the deep links.",
)
async def update_notify_settings(body: NotifySettingsUpdate, db: Database, ctx: Ctx) -> NotifySettingsOut:
    return await inbox.update_settings(db, ctx, body)

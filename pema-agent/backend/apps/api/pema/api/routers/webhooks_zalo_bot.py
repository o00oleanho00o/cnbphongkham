"""Zalo Bot API webhook receiver (package C1 implements).

The request is authenticated by ``ChannelPort.verify_webhook`` (secret token header), not by a cookie. The
path carries no clinic (single tenant: one installation is one clinic). Duplicate deliveries are dropped on
``update_id`` (``agent.channel_update_seen``). Webhook and ``getUpdates`` polling are mutually exclusive on
the Bot API: the account runs in one mode only.

Wiring seam (set on ``app.state`` by the composition root, package G; missing = 503, nothing is accepted):
``zalo_bot_webhook``, a ``pema.channels.zalo_bot.webhook.ZaloBotWebhookService``. All the logic (account
lookup, secret check, de-duplication, routing) lives in that service, so this file stays a thin adapter.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Request

from pema.api.deps import ERROR_RESPONSES
from pema.channels.zalo_bot.webhook import ZaloBotWebhookService
from pema_contracts.conversations import WebhookAck
from pema_contracts.errors import DomainError, ErrorCode

router = APIRouter(tags=["webhooks"], responses=ERROR_RESPONSES)


@router.post(
    "/webhooks/zalo-bot/{account_id}",
    response_model=WebhookAck,
    summary="Zalo Bot API update receiver (de-duplicates on update_id)",
)
async def receive_zalo_bot_update(
    account_id: str,
    request: Request,
    payload: Annotated[dict[str, Any], Body(description="Raw Bot API update.")],
) -> WebhookAck:
    service: ZaloBotWebhookService | None = getattr(request.app.state, "zalo_bot_webhook", None)
    if service is None:
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Kênh Zalo Bot chưa sẵn sàng.")
    return await service.receive(account_id, request.headers, await request.body(), payload)

"""Zalo Bot API webhook receiver (package C1 implements).

The request is authenticated by ``ChannelPort.verify_webhook`` (secret token header), not by a cookie.
The clinic is resolved from the slug through ``ctx.resolve_clinic``. Duplicate deliveries are dropped on
``update_id`` (``agent.channel_update_seen``). Webhook and ``getUpdates`` polling are mutually
exclusive on the Bot API: the account runs in one mode only.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body

from pema.api.deps import ERROR_RESPONSES, not_implemented
from pema_contracts.conversations import WebhookAck

router = APIRouter(tags=["webhooks"], responses=ERROR_RESPONSES)


@router.post(
    "/webhooks/zalo-bot/{clinic_slug}/{account_id}",
    response_model=WebhookAck,
    summary="Zalo Bot API update receiver (de-duplicates on update_id)",
)
async def receive_zalo_bot_update(
    clinic_slug: str,
    account_id: str,
    payload: Annotated[dict[str, Any], Body(description="Raw Bot API update.")],
) -> WebhookAck:
    not_implemented()

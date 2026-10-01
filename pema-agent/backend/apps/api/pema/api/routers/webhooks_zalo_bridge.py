"""Inbound events from the Node zca-js bridge of a personal account (package C2 implements).

The bridge POSTs each Zalo event (message, friend request, reconnect state) with an HMAC signature
(``PEMA_ZALO_BRIDGE_SECRET``); ``ChannelPort.verify_webhook`` checks it in constant time. Off unless
``PEMA_ZALO_PERSONAL_ENABLED`` is true. The outbound direction (send, QR login, friends) is API -> bridge.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body

from pema.api.deps import ERROR_RESPONSES, not_implemented
from pema_contracts.conversations import WebhookAck

router = APIRouter(tags=["webhooks"], responses=ERROR_RESPONSES)


@router.post(
    "/webhooks/zalo-bridge/{clinic_slug}/{account_id}",
    response_model=WebhookAck,
    summary="Personal-account bridge event receiver (HMAC signed)",
)
async def receive_zalo_bridge_event(
    clinic_slug: str,
    account_id: str,
    payload: Annotated[dict[str, Any], Body(description="Bridge event envelope.")],
) -> WebhookAck:
    not_implemented()

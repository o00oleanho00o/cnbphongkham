"""Inbound events from the Node zca-js bridge of a personal account (package C2 implements).

The bridge POSTs each Zalo event (message, friend event, credential update, account state) with an HMAC
signature
(``PEMA_ZALO_BRIDGE_SECRET``, ``X-Pema-Timestamp`` + ``X-Pema-Signature``); the signature is verified in
constant
time over the RAW body before anything else happens. Off unless ``PEMA_ZALO_PERSONAL_ENABLED`` is true.
The outbound
direction (send, QR login, friends) is API -> bridge.

``clinic_slug`` is the clinic slug, or the clinic id as text (the worker, which cannot read ``clinic.*``,
starts
accounts and only knows the id). The path never carries a secret; the body of a ``message`` event carries
personal
content and the body of ``credential_updated`` a secret: neither is logged.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Request

from pema.api.deps import ERROR_RESPONSES
from pema.channels.zalo_personal.bridge_signing import verify_signature
from pema.channels.zalo_personal.services import get_c2
from pema.shared.logger import create_logger
from pema_contracts.conversations import WebhookAck
from pema_contracts.errors import DomainError, ErrorCode

router = APIRouter(tags=["webhooks"], responses=ERROR_RESPONSES)

log = create_logger("webhooks.zalo-bridge")


@router.post(
    "/webhooks/zalo-bridge/{clinic_slug}/{account_id}",
    response_model=WebhookAck,
    summary="Personal-account bridge event receiver (HMAC signed)",
)
async def receive_zalo_bridge_event(
    clinic_slug: str,
    account_id: str,
    payload: Annotated[dict[str, Any], Body(description="Bridge event envelope.")],
    request: Request,
) -> WebhookAck:
    services = get_c2(request)
    if not services.flag_enabled():
        raise DomainError(ErrorCode.CHANNEL_UNAVAILABLE, "Tài khoản cá nhân đang bị tắt bằng cờ cấu hình.")

    secret = services.bridge_secret()
    raw = await request.body()
    if not secret or not verify_signature(secret, request.headers, raw):
        log.warning("bridge event rejected: bad signature", account_id=account_id)
        raise DomainError(ErrorCode.CHANNEL_WEBHOOK_REJECTED, "Chữ ký của bridge không hợp lệ.")

    clinic_id = await services.resolve_clinic(clinic_slug)
    if clinic_id is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy phòng khám.")

    return await services.events.handle(clinic_id, account_id, payload)

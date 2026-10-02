"""Zalo Bot API webhook receiver (webhook mode of a bot account).

New module (no TypeScript source: the original only long polled). A delivery is ``POST
/api/v1/webhooks/zalo-bot/{account_id}`` with the header ``X-Bot-Api-Secret-Token`` (the
``secret_token`` given to ``setWebhook``) and a body ``{"ok": true, "result": {event_name, message}}``.

Order of the steps, and why:

1. Find the RUNNING channel of the account in the installation clinic (single tenant: one installation is one
  clinic, so the path carries no clinic). An account that is not running and a wrong secret answer the SAME
  401 (``channel_webhook_rejected``): the endpoint is public, so it must not tell a caller which accounts
  exist. The only authentication is the secret token.
2. ``ZaloBotChannel.verify_webhook`` (constant time, fail closed when no secret is configured) BEFORE any
  parsing.
3. De-duplicate on ``update_id`` (``agent.channel_update_seen``). Zalo retries a delivery it did not get a 2xx
  for; the second copy answers ``duplicate: true`` and does nothing.
4. Route (record + batch + enqueue). The turn does NOT run in this request: it runs in the worker through the
  ``TurnQueue``. If routing raises, the dedupe mark is REMOVED before the error propagates (HTTP 5xx), so
  Zalo's retry is not discarded as a duplicate of a message that was never recorded. The Inbox write is strict
  here for the same reason (``strict_inbox=True``): a retry is possible, so a failed Inbox write must fail the
  request.

Keeping the handler quick matters: Zalo treats a slow answer as a failure and retries.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

from pema.channels.zalo_bot.bot_message_router import BotMessageRouter
from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate, unwrap_webhook_payload
from pema.channels.zalo_bot.zalo_bot_update_parser import doi_update_sang_parsed_message
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger
from pema_contracts.channel import ChannelKind, ChannelRegistry
from pema_contracts.conversations import WebhookAck
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.installation import installation_clinic_id

_log = create_logger("zalo-bot-webhook")

_REJECTED = "Webhook bị từ chối."


class UpdateDedupe(Protocol):
    async def first_seen(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        """``True`` when this update id was NOT seen before (and is now marked as seen)."""
        ...

    async def forget(self, clinic_id: UUID, account_id: str, update_id: str) -> None: ...


class InMemoryUpdateDedupe:
    def __init__(self) -> None:
        self._seen: set[tuple[UUID, str, str]] = set()

    async def first_seen(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        key = (clinic_id, account_id, update_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    async def forget(self, clinic_id: UUID, account_id: str, update_id: str) -> None:
        self._seen.discard((clinic_id, account_id, update_id))


class PostgresUpdateDedupe:
    """``agent.channel_update_seen`` (primary key ``(clinic_id, account_id, update_id)``) through the
    ``be_app`` database. ``INSERT ... ON CONFLICT DO NOTHING RETURNING`` is the atomic "first one wins"; two
    concurrent deliveries of the same update cannot both pass."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def first_seen(self, clinic_id: UUID, account_id: str, update_id: str) -> bool:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    text(
                        "INSERT INTO agent.channel_update_seen (clinic_id, account_id, update_id) "
                        "VALUES (:clinic_id, :account_id, :update_id) "
                        "ON CONFLICT DO NOTHING RETURNING update_id"
                    ),
                    {"clinic_id": clinic_id, "account_id": account_id, "update_id": update_id},
                )
            ).first()
        return row is not None

    async def forget(self, clinic_id: UUID, account_id: str, update_id: str) -> None:
        async with self._db.session() as session:
            await session.execute(
                text(
                    "DELETE FROM agent.channel_update_seen "
                    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND update_id = :update_id"
                ),
                {"clinic_id": clinic_id, "account_id": account_id, "update_id": update_id},
            )

    async def purge(self, clinic_id: UUID, older_than: timedelta = timedelta(days=7)) -> int:
        """Delete the marks older than ``older_than`` (Zalo does not retry after a few hours). To be called
        from a periodic job (open item for package G: no scheduler of C1 owns it)."""
        async with self._db.session() as session:
            result = await session.execute(
                text(
                    "DELETE FROM agent.channel_update_seen "
                    "WHERE clinic_id = :clinic_id AND seen_at < now() - make_interval(secs => :seconds)"
                ),
                {"clinic_id": clinic_id, "seconds": older_than.total_seconds()},
            )
        return int(result.rowcount or 0)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]


class ZaloBotWebhookService:
    def __init__(
        self,
        *,
        registry: ChannelRegistry,
        router: BotMessageRouter,
        dedupe: UpdateDedupe,
        clinic_id: UUID | None = None,
    ) -> None:
        self._clinic_id = clinic_id
        """The installation clinic; ``None``: the process-wide installation id, read per delivery."""
        self._registry = registry
        self._router = router
        self._dedupe = dedupe

    async def receive(
        self,
        account_id: str,
        headers: Mapping[str, str],
        body: bytes,
        payload: Mapping[str, object],
    ) -> WebhookAck:
        clinic_id = self._clinic_id if self._clinic_id is not None else installation_clinic_id()
        channel = self._registry.get_running(clinic_id, account_id)
        if channel is None or channel.kind is not ChannelKind.ZALO_BOT:
            _log.warning("Webhook cho account không chạy", account_id=account_id)
            raise DomainError(ErrorCode.CHANNEL_WEBHOOK_REJECTED, _REJECTED)
        if not channel.verify_webhook(headers, body):
            _log.warning("Webhook sai secret", account_id=account_id)
            raise DomainError(ErrorCode.CHANNEL_WEBHOOK_REJECTED, _REJECTED)

        try:
            update = ZaloBotUpdate.model_validate(unwrap_webhook_payload(payload))
        except ValidationError:
            # Authenticated but unreadable: acknowledge so Zalo does not retry a body that will never parse.
            _log.warning("Webhook có thân không đọc được", account_id=account_id)
            return WebhookAck(ok=True)

        parsed = doi_update_sang_parsed_message(account_id, update)
        if parsed is None:
            # Not a user message (another bot, no message): nothing to record. Acknowledge.
            return WebhookAck(ok=True)

        if not await self._dedupe.first_seen(clinic_id, account_id, parsed.update_id):
            return WebhookAck(ok=True, duplicate=True)
        try:
            await self._router.route_bot_update(clinic_id, account_id, channel, update, strict_inbox=True)
        except BaseException:
            await self._dedupe.forget(clinic_id, account_id, parsed.update_id)
            raise
        return WebhookAck(ok=True)

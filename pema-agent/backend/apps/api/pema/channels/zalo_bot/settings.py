"""Settings of the Zalo Bot channel, read from environment variables ``PEMA_ZALO_BOT_*``.

New module (no TypeScript source). The ``PEMA_`` platform settings of ``pema.config.env`` are package A's; the
bot-specific ones live here so package C1 does not edit that file. A bot account's TOKEN is NOT here: it is
entered on the admin screen, stored encrypted (``AccountStore.set_bot_token``) and never read from the
environment, except by the probe CLI (``PEMA_ZALO_BOT_PROBE_TOKEN``, one throwaway test bot).

Webhook secret: derived, not stored. ``derive_webhook_secret`` = HMAC-SHA256 of ``clinic|account`` keyed with
``PEMA_SECRET_ENCRYPTION_KEY`` under a fixed label, 64 hex characters (the Bot API takes 8 to 256). The runner
sends it with ``setWebhook`` each time the account starts; ``ZaloBotChannel.verify_webhook`` compares it in
constant time.
"""

from __future__ import annotations

import hashlib
import hmac
from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from pema.config.env import get_settings
from pema.config.secret_cipher import SecretKeyMissingError


class ZaloBotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEMA_ZALO_BOT_", env_file=".env", extra="ignore")

    mode: Literal["polling", "webhook"] = "polling"
    """``polling`` (``getUpdates`` long poll) or ``webhook``. They are mutually exclusive on the Bot API: an
    account runs in ONE mode and the runner removes a stray webhook before it polls."""

    api_base: str = "https://bot-api.zaloplatforms.com"

    webhook_base_url: str | None = None
    """Public HTTPS origin of the API (no trailing slash), e.g. ``https://cskh.example.test``. Required in
    webhook mode; Zalo rejects local and private addresses."""

    probe_token: SecretStr | None = None
    """Token of ONE test bot, read only by ``python -m pema.channels.zalo_bot.kiem_chung_bot_api``."""


@lru_cache
def get_zalo_bot_settings() -> ZaloBotSettings:
    return ZaloBotSettings()


def derive_webhook_secret(clinic_id: UUID, account_id: str) -> str:
    key = get_settings().secret_encryption_key
    if key is None:
        raise SecretKeyMissingError("PEMA_SECRET_ENCRYPTION_KEY is not set; cannot derive a webhook secret")
    message = f"zalo-bot-webhook|{clinic_id}|{account_id}".encode()
    return hmac.new(key.get_secret_value().encode("utf-8"), message, hashlib.sha256).hexdigest()


def webhook_url_for(base_url: str, clinic_slug: str, account_id: str) -> str:
    return f"{base_url.rstrip('/')}/api/v1/webhooks/zalo-bot/{clinic_slug}/{account_id}"

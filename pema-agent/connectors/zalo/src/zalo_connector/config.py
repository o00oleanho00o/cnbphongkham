"""The service's settings, all read once from the environment.

``RICH_TEXT`` and ``POLL_TIMEOUT_S`` replace the plugin settings ``rich_text`` and ``poll_timeout_s``,
``PUBLIC_URL`` the plugin setting ``public_url``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

CONNECTOR_NAME_RULE: Final = "abcdefghijklmnopqrstuvwxyz0123456789_-"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Config:
    agent_url: str
    callback_url: str
    connector_name: str
    connector_key: str
    """Empty: the service runs (admin pages, polling) but cannot talk to the agent."""
    secret_key: str
    data_dir: Path
    bridge_dir: Path
    ui_dir: Path
    crm_jwks_url: str
    sso_issuer: str
    sso_audience: str
    public_url: str
    rich_text: bool
    poll_timeout_s: int
    port: int
    part_pause_s: tuple[float, float]
    """Random pause between the parts of one long reply (a personal account that sends parts back to back
    can be banned); (0, 0) sends at once."""

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        values = os.environ if env is None else env

        def read(name: str, default: str = "") -> str:
            return (values.get(name) or default).strip()

        secret_key = read("ZALO_SECRET_KEY")
        if not secret_key:
            raise ConfigError("ZALO_SECRET_KEY is not set: it seals the bot tokens and logins in the store")
        name = read("CONNECTOR_NAME", "zalo")
        if not name or len(name) > 32 or any(c not in CONNECTOR_NAME_RULE for c in name):
            raise ConfigError("CONNECTOR_NAME has 1 to 32 characters of a-z, 0-9, '_' and '-'")
        port = int(read("PORT", "8089"))
        poll = int(read("POLL_TIMEOUT_S", "30"))
        low, high = float(read("PART_PAUSE_MIN_S", "10")), float(read("PART_PAUSE_MAX_S", "20"))
        if low < 0 or high < low:
            raise ConfigError("PART_PAUSE_MIN_S and PART_PAUSE_MAX_S need 0 <= min <= max")
        return cls(
            agent_url=read("AGENT_URL", "http://agent:8088").rstrip("/"),
            callback_url=read("CALLBACK_URL", "http://zalo:8089").rstrip("/"),
            connector_name=name,
            connector_key=read("CONNECTOR_KEY"),
            secret_key=secret_key,
            data_dir=Path(read("ZALO_DATA_DIR", "/data")),
            bridge_dir=Path(read("ZALO_BRIDGE_DIR", "/app/bridge")),
            ui_dir=Path(read("ZALO_UI_DIR", "/app/ui/dist")),
            crm_jwks_url=read("CRM_JWKS_URL"),
            sso_issuer=read("SSO_ISSUER", "pema-clinic"),
            sso_audience=read("SSO_AUDIENCE", "pema-agent"),
            public_url=read("PUBLIC_URL").rstrip("/"),
            rich_text=read("RICH_TEXT", "true").lower() not in ("0", "false", "no", "off"),
            poll_timeout_s=max(5, min(60, poll)),
            port=port,
            part_pause_s=(low, high),
        )

# ported from: src/config/env.ts (platform subset)
"""Platform settings read from environment variables (prefix ``PEMA_``) or a local ``.env``.

Forced deviation: zod ``envSchema`` becomes ``pydantic-settings``. This module carries only the
platform settings every process needs (database, redis, logging, secrets). The ~70 TUNING parameters
and the LLM settings of the original ``env.ts`` are NOT here: they are ported by D1 into
``pema.config.tuning_definitions`` / ``runtime_tuning_settings`` and keep their ORIGINAL (unprefixed)
env names as defaults, with the override stored in ``agent.runtime_settings``.

Nothing here has a real secret as default; secrets are ``None`` until configured. ``.env`` is never
committed (see ``infra/.env.example``). Each runtime role has its own connection URL:

* ``database_url``         role ``be_app``       (API process; RLS applies)
* ``worker_database_url``  role ``agent_worker`` (worker process; reads clinic data only via views)
* ``migration_database_url`` owner role, used only by Alembic.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEMA_", env_file=".env", extra="ignore")

    environment: str = "dev"

    # logging (LOG_LEVEL, LOG_FILE_ENABLED, LOG_FILE_KEEP_DAYS of env.ts)
    log_level: str = "INFO"
    log_file_enabled: bool = False
    log_file_keep_days: int = 14
    data_dir: Path = Path(".local/data")
    """Local data (logs, temp files). Never committed (``.local/`` is git-ignored)."""

    bot_timezone: str = "Asia/Ho_Chi_Minh"
    """``BOT_TIMEZONE``: zone for 'today', cron and the daily proactive cap."""

    database_url: str = "postgresql+psycopg://be_app@localhost:5432/pema"
    worker_database_url: str = "postgresql+psycopg://agent_worker@localhost:5432/pema"
    migration_database_url: str = "postgresql+psycopg://postgres@localhost:5432/pema"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr | None = None
    session_cookie_name: str = "pema_session"
    session_ttl_minutes: int = 480

    secret_encryption_key: SecretStr | None = None
    """Key of ``secret_cipher`` (AES-GCM) for bot tokens, Zalo credentials, MCP headers, API keys."""

    zalo_personal_enabled: bool = False
    zalo_bridge_url: str = "http://localhost:8200"
    zalo_bridge_secret: SecretStr | None = None

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()

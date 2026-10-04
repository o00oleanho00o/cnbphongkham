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

from pydantic import Field, SecretStr, field_validator
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

    crm_runner_interval_seconds: int = 900
    """How often the API process runs the CRM rules for every clinic (0 turns the runner off). The runner
    reads ``clinic.*``, so it lives in the API process (role ``be_app``), not in the worker."""

    # --- data retention (pema.retention; Decree 13/2023). Days per group; 0 keeps the data forever. -------
    # The real periods are the clinic owner's decision: the defaults keep clinical data and messages
    # (0) and give only purely technical data a short life. ``None`` = follow the tuning key named below.
    retention_interval_seconds: int = Field(default=86_400, ge=0)
    """Gap between two retention runs of a process (0 turns the periodic run off; the CLI still works)."""
    retention_batch_size: int = Field(default=500, ge=1, le=10_000)
    """Rows deleted per statement (one small transaction each)."""
    retention_history_days: int = Field(default=0, ge=0)
    """``agent.history`` (conversation context of the agent) and the images/descriptions of those rows, plus
    the rolling summary of threads idle for that long. 0 = keep."""
    retention_memory_days: int = Field(default=0, ge=0)
    """``agent.memories`` (facts the agent learned). 0 = keep."""
    retention_message_days: int = Field(default=0, ge=0)
    """``clinic.message`` of conversations closed for that long, then the empty closed conversations. Open
    review items protect their conversation and messages. 0 = keep."""
    retention_usage_days: int = Field(default=0, ge=0)
    """``agent.usage`` (token ledger, no text) and, by cascade, its trace steps. 0 = keep."""
    retention_trace_days: int | None = Field(default=None, ge=0)
    """``agent.usage_steps`` (raw tool output and model text). Unset = ``AGENT_TRACE_RETENTION_DAYS`` (7)."""
    retention_media_days: int | None = Field(default=None, ge=0)
    """Image files on the local volume and ``agent.image_descriptions``. Unset = ``MEDIA_RETENTION_DAYS``
    (7)."""
    retention_job_run_days: int = Field(default=30, ge=0)
    """Finished rows of ``agent.job_runs`` (scheduler delivery log)."""
    retention_auth_session_days: int = Field(default=1, ge=0)
    """Days after expiry before an expired dashboard session row is deleted."""
    retention_link_code_days: int = Field(default=7, ge=0)
    """Days after expiry (or use) before an identity-link code (a hash) is deleted."""
    retention_link_attempt_days: int = Field(default=30, ge=0)
    """``clinic.identity_link_attempt`` (failure log of the link flow); never younger than one hour."""

    zalo_personal_enabled: bool = False
    zalo_bridge_url: str = "http://localhost:8200"
    zalo_bridge_secret: SecretStr | None = None

    @field_validator("retention_trace_days", "retention_media_days", mode="before")
    @classmethod
    def _empty_means_unset(cls, value: object) -> object:
        """docker-compose passes an unset variable as an empty string: that means "follow the tuning key"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()

# ported from: src/config/env.ts (platform subset)
"""Platform settings read from environment variables (prefix ``PEMA_``) or a local ``.env``.

Forced deviation: zod ``envSchema`` becomes ``pydantic-settings``. This module carries only the
platform settings of the clinic API (database, redis, logging, secrets). The tuning parameters and LLM
settings of the original ``env.ts`` belong to the agent service, not here.

Nothing here has a real secret as default; secrets are ``None`` until configured. ``.env`` is never
committed (see ``infra/.env.example``). Each runtime role has its own connection URL:

* ``database_url``         role ``be_app``       (API process)
* ``migration_database_url`` owner role, used only by Alembic.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import UUID

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

    # --- single tenant (ST-A): one installation is ONE clinic, with its own database. -------------------
    clinic_name: str = "Pema Clinic"
    """``PEMA_CLINIC_NAME``: name of the one clinic. Read by the migration/bootstrap
    (``clinic.ensure_clinic``) when the database has no clinic yet; an installed clinic is never renamed."""
    clinic_id: UUID | None = None
    """``PEMA_CLINIC_ID`` (optional): the installation id. Unset = read once from ``clinic.clinic``. When
    set it is the id the migration creates the clinic with, and processes use it without asking the DB."""

    database_url: str = "postgresql+psycopg://be_app@localhost:5432/pema"
    migration_database_url: str = "postgresql+psycopg://postgres@localhost:5432/pema"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr | None = None
    session_cookie_name: str = "pema_session"
    session_ttl_minutes: int = 480

    crm_runner_interval_seconds: int = 900
    """How often the API process runs the CRM rules for every clinic (0 turns the runner off). The runner
    reads ``clinic.*``, so it lives in the API process (role ``be_app``), not in the worker."""

    # --- data retention (pema.retention; Decree 13/2023). Days per group; 0 keeps the data forever. -------
    # The real periods are the clinic owner's decision: the defaults keep clinical data and give only purely
    # technical data a short life.
    retention_interval_seconds: int = Field(default=86_400, ge=0)
    """Gap between two retention runs of a process (0 turns the periodic run off; the CLI still works)."""
    retention_batch_size: int = Field(default=500, ge=1, le=10_000)
    """Rows deleted per statement (one small transaction each)."""
    retention_auth_session_days: int = Field(default=1, ge=0)
    """Days after expiry before an expired dashboard session row is deleted."""

    @field_validator("clinic_id", mode="before")
    @classmethod
    def _empty_clinic_id_is_unset(cls, value: object) -> object:
        """docker-compose passes an unset variable as an empty string: it means "read it from the DB"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("clinic_name", mode="before")
    @classmethod
    def _empty_clinic_name_is_default(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return "Pema Clinic"
        return value

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()

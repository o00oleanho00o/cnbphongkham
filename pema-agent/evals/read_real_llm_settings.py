# ported from: evals/read-real-llm-settings.ts
"""Read the LLM configuration that is RUNNING FOR REAL: the DB over the environment, the same rule as
``get_effective_llm_settings()`` of production.

WHY IT MUST EXIST, a lesson paid for with one false alarm: the first version of the evals only read the
environment. But the model is configured THROUGH THE DASHBOARD (saved in ``runtime_settings``) and the
environment is only a fallback layer. A dev machine had an old ``LLM_MODEL`` left in the environment while the
DB held the right value, so the eval called with the wrong model name, the router answered 404, and the wrong
conclusion was "the bot is broken" while the bot ran perfectly well.

General lesson: an eval suite that reads its configuration from a DIFFERENT source than production measures a
different system from the one that is running.

READ-ONLY: the only statement issued is the ``SELECT`` of ``SqlRuntimeSettingsStore.load_all``; nothing is
ever written to the real DB. The agent turns run on in-memory settings.

Forced deviations: SQLite file (``DATA_DIR/zalo-agent.db`` opened ``readOnly``) becomes the Postgres table
``agent.runtime_settings`` of ONE clinic, reached through ``PEMA_EVAL_DATABASE_URL`` + ``PEMA_EVAL_CLINIC_ID``
(both unset = "no DB yet", the normal case of a fresh machine: fall back to the environment). The loader is
injectable so the module is testable without a database; ``AES-GCM`` decryption is ``decrypt_with`` with
``PEMA_SECRET_ENCRYPTION_KEY`` (the original used ``CREDENTIALS_ENCRYPTION_KEY``).
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID

from pema.config.secret_cipher_core import decrypt_with

SettingsLoader = Callable[[], Awaitable[dict[str, str]]]
"""Returns every ``runtime_settings`` row of the clinic (key -> stored value)."""

KHOA = ("llm_provider", "llm_base_url", "llm_model", "llm_api_key")


@dataclass
class LlmThat:
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    tu_db: list[str] = field(default_factory=list[str])
    """Which fields came from the DB: told to the person running, so they know which source won."""


def real_settings_loader() -> SettingsLoader | None:
    """Loader of the real DB from the environment; ``None`` when it is not configured or not reachable by
    construction (no URL / no clinic id): the evals then fall back to the environment alone."""
    url = os.environ.get("PEMA_EVAL_DATABASE_URL")
    clinic = os.environ.get("PEMA_EVAL_CLINIC_ID")
    if not url or not clinic:
        return None
    try:
        clinic_id = UUID(clinic)
    except ValueError:
        return None

    async def load() -> dict[str, str]:
        from pema.config.runtime_settings_store import SqlRuntimeSettingsStore
        from pema.core.db import ClinicDatabase

        db = ClinicDatabase(url, pool_size=1)
        try:
            return await SqlRuntimeSettingsStore(db).load_all(clinic_id)
        finally:
            await db.engine.dispose()

    return load


async def doc_llm_tu_db_that(
    loader: SettingsLoader | None = None, encryption_key: str | None = None
) -> LlmThat:
    ra = LlmThat()
    # No DB yet (a freshly cloned machine) is normal: fall back to the environment entirely
    load = loader if loader is not None else real_settings_loader()
    if load is None:
        return ra

    try:
        rows = await load()
    except Exception:
        # DB unreachable or the table missing (old schema): fall back to the environment
        return ra

    key = encryption_key if encryption_key is not None else os.environ.get("PEMA_SECRET_ENCRYPTION_KEY")
    for khoa in KHOA:
        v = rows.get(khoa)
        if not v:
            continue

        if khoa == "llm_api_key":
            if not key:
                continue
            try:
                ra.api_key = decrypt_with(key, v)
            except Exception:  # noqa: S112
                # A wrong encryption key is skipped and the environment key is used: reporting an error here
                # would only make the person running believe the eval suite is broken.
                continue
            ra.tu_db.append("apiKey")
            continue

        if khoa == "llm_provider":
            ra.provider = v
            ra.tu_db.append("provider")
        elif khoa == "llm_base_url":
            ra.base_url = v
            ra.tu_db.append("baseUrl")
        elif khoa == "llm_model":
            ra.model = v
            ra.tu_db.append("model")

    return ra

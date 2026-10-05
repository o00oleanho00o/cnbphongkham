# ported from: evals/read-real-search-settings.ts
"""Read the WEB SEARCH configuration that is running for real (provider + Brave key).

The same lesson as ``read_real_llm_settings``, only the pain is elsewhere, and this time it really bit, on
2026-08-06:

The real bot had ``search_provider = brave`` on the dashboard so search worked. The eval suite ran on an EMPTY
temporary DB with no Brave key, so it fell back to DuckDuckGo. That day DuckDuckGo returned 0 results for
EVERY query, so the research case went red with the reason "did not call web_fetch", an entirely wrong
diagnosis: the model did search, it just never received a URL to open. It nearly led to the wrong conclusion
that the persona rule just edited made the model worse.

In short: an eval suite that reads configuration from a DIFFERENT source than production measures a different
system from the one that is running, and that holds for EVERY setting, not only the model.

READ-ONLY, same loader as the LLM settings (see there for the forced deviations from SQLite to Postgres).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from evals.read_real_llm_settings import SettingsLoader, real_settings_loader
from pema.config.secret_cipher_core import decrypt_with

KHOA_PROVIDER = "search_provider"
KHOA_BRAVE = "search_brave_api_key"


@dataclass
class TraCuuThat:
    provider: str | None = None
    brave_api_key: str | None = None
    tu_db: list[str] = field(default_factory=list[str])
    """What came from the DB: told to the person running, so they know which source won."""


async def doc_tra_cuu_tu_db_that(
    loader: SettingsLoader | None = None, encryption_key: str | None = None
) -> TraCuuThat:
    ra = TraCuuThat()
    load = loader if loader is not None else real_settings_loader()
    if load is None:
        return ra

    try:
        rows = await load()
    except Exception:
        # Old schema without the table, or locked: fall back to the defaults
        return ra

    provider = rows.get(KHOA_PROVIDER)
    if provider:
        ra.provider = provider
        ra.tu_db.append("searchProvider")

    brave = rows.get(KHOA_BRAVE)
    key = encryption_key if encryption_key is not None else os.environ.get("PEMA_SECRET_ENCRYPTION_KEY")
    if brave and key:
        try:
            ra.brave_api_key = decrypt_with(key, brave)
            ra.tu_db.append("braveKey")
        except Exception:  # noqa: S110 - a wrong encryption key is skipped on purpose, see below
            # A wrong encryption key is skipped: the eval falls back to DuckDuckGo, and the precondition check
            # says so clearly if that route is dead too
            pass

    return ra

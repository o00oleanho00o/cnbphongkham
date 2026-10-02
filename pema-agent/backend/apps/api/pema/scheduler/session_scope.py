"""Join an open unit of work or open one (new module, no zalo-agent source).

The original stores were bound to ONE synchronous SQLite handle, so "bookkeeping that must happen together"
(``finishRun`` + ``markRun`` + ``resetDeliveryAttempts``) was three separate statements that could be
interrupted between two of them. On Postgres each store method accepts an optional open ``AsyncSession`` so
the callers that need atomicity (claim + open run, conclude) compose the statements in ONE transaction, and
the callers that do not simply let the method open its own ``db.session()``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.shared.zone_time import to_iso_z


@asynccontextmanager
async def use_session(
    db: ClinicDatabase, clinic_id: UUID, session: AsyncSession | None
) -> AsyncGenerator[AsyncSession]:
    if session is not None:
        yield session
        return
    async with db.session() as opened:
        yield opened


def iso_or_none(value: datetime | None) -> str | None:
    """A ``timestamptz`` column as the UTC ISO string (``...Z``) the original stored."""
    return None if value is None else to_iso_z(value)


def parse_utc(value: str | None) -> datetime | None:
    """The reverse of ``iso_or_none``: a UTC ISO string to an aware datetime."""
    if value is None:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

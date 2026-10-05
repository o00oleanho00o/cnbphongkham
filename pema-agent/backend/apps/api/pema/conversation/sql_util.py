"""Small SQL helpers shared by the stores of D2 (no zalo-agent source file).

* ``like_pattern``: zalo-agent built ``%${query}%`` by hand and let a ``%`` or ``_`` typed by the user act
  as a wildcard. Here the text is escaped so that a search for ``50%`` finds ``50%``; the queries pair it
  with ``ILIKE ... ESCAPE '\\'``.
* ``affected_rows``: ``result.changes`` of ``node:sqlite``. ``AsyncSession.execute`` is typed as a generic
  ``Result`` although a DML statement returns a ``CursorResult``; this narrows it in one place.
"""

from __future__ import annotations

from sqlalchemy import CursorResult
from sqlalchemy.engine import Result


def like_pattern(query: str) -> str:
    """``%query%`` with ``\\``, ``%`` and ``_`` of ``query`` escaped (use with ``ESCAPE '\\'``)."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def affected_rows(result: Result[tuple[object, ...]] | object) -> int:
    """Rows changed by an INSERT/UPDATE/DELETE (``changes`` in ``node:sqlite``)."""
    if isinstance(result, CursorResult):
        return int(result.rowcount)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    raise TypeError("affected_rows needs the result of a DML statement")

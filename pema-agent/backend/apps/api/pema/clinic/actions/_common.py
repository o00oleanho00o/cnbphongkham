"""Helpers shared by the action modules: clock, optimistic locking, escaping, errors.

New module. Actions are plain ``async`` functions ``(db, ctx, ...) -> DTO``. ``db`` is a
``pema.core.db.ClinicDatabase`` (role ``be_app``); each action opens its own unit of work with
``db.session(ctx.clinic_id)`` so RLS is always set. Actions that must compose into one transaction (CRM task
resolve + booking, review approve + booking) share private ``_*`` helpers that take a session.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Final

from sqlalchemy.orm.exc import StaleDataError

from pema_contracts.errors import DomainError, ErrorCode

type Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


_clock: Clock = _system_clock

VERSION_CONFLICT_MESSAGE: Final = "Bản ghi đã được người khác thay đổi. Hãy tải lại rồi thử lại."
NOT_FOUND_MESSAGE: Final = "Không tìm thấy dữ liệu trong phòng khám này."


def now() -> datetime:
    """Aware UTC now (the clock tests replace with ``use_clock``)."""
    return _clock()


@contextmanager
def use_clock(clock: Clock) -> Generator[None]:
    """Replace the clock for the duration of a ``with`` block (tests: the demo day 2026-09-20)."""
    global _clock
    previous = _clock
    _clock = clock
    try:
        yield
    finally:
        _clock = previous


def not_found(what: str = "") -> DomainError:
    suffix = f" ({what})" if what else ""
    return DomainError(ErrorCode.NOT_FOUND, NOT_FOUND_MESSAGE + suffix)


def check_version(actual: int, expected: int) -> None:
    """Optimistic lock: the client edited version ``expected``; the row is at ``actual``."""
    if actual != expected:
        raise DomainError(
            ErrorCode.VERSION_CONFLICT,
            VERSION_CONFLICT_MESSAGE,
            details={"current_version": actual},
        )


@contextmanager
def lost_race_is_conflict() -> Generator[None]:
    """A concurrent UPDATE between our read and our flush surfaces as ``StaleDataError``
    (``version_id_col``); it is the same 409 as a stale client version."""
    try:
        yield
    except StaleDataError as exc:
        raise DomainError(ErrorCode.VERSION_CONFLICT, VERSION_CONFLICT_MESSAGE) from exc


def escape_like(value: str) -> str:
    """Escape ``%``, ``_`` and the escape char itself for a ``LIKE ... ESCAPE '\\'`` pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

"""Structural guard: no commit of a clinic mutation without an audit row.

New module. "Every mutation is audited" is easy to promise and easy to forget, so it is enforced where it
cannot be skipped: SQLAlchemy session events.

* ``before_flush``: if the unit of work inserts, updates or deletes any ``clinic.*`` ORM object other than
  ``AuditLog`` it is marked as a mutation; adding an ``AuditLog`` marks it as audited;
* ``before_commit``: a session that mutated without auditing raises ``AuditMissingError`` and the
  transaction rolls back.

Scope: it sees ORM mutations only. Raw SQL ``INSERT``/``UPDATE`` through ``text()`` is invisible to it, so
the actions use the ORM for writes; the SECURITY DEFINER functions of ``clinic_agent`` write their own audit
row inside SQL.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from pema.clinic.models import AuditLog, Base

_MUTATED = "pema_audit_mutated"
_AUDITED = "pema_audit_written"
_installed = False


class AuditMissingError(RuntimeError):
    """A transaction changed clinic data without writing an audit row."""


def _is_clinic_object(obj: object) -> bool:
    return isinstance(obj, Base) and not isinstance(obj, AuditLog)


def _before_flush(session: Session, _ctx: object, _instances: object) -> None:
    if any(isinstance(obj, AuditLog) for obj in session.new):
        session.info[_AUDITED] = True
    changed = (
        any(_is_clinic_object(o) for o in session.new)
        or any(_is_clinic_object(o) for o in session.deleted)
        or any(_is_clinic_object(o) and session.is_modified(o) for o in session.dirty)
    )
    if changed:
        session.info[_MUTATED] = True


def _before_commit(session: Session) -> None:
    if session.in_nested_transaction():
        return  # releasing a SAVEPOINT is not the commit of the unit of work
    # ``before_commit`` runs BEFORE the final flush: look at what is still pending as well
    _before_flush(session, None, None)
    if session.info.get(_MUTATED) and not session.info.get(_AUDITED):
        raise AuditMissingError("clinic data changed without an audit_log row in the same transaction")


def _reset(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:  # the outermost transaction ended (commit or rollback)
        session.info.pop(_MUTATED, None)
        session.info.pop(_AUDITED, None)


def install_audit_guard() -> None:
    """Idempotent; called when ``pema.clinic.audit`` is imported."""
    global _installed
    if _installed:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "before_commit", _before_commit)
    event.listen(Session, "after_transaction_end", _reset)
    _installed = True

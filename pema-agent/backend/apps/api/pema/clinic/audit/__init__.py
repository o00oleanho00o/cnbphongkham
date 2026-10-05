"""Append-only audit_log writer and the structural guard that every mutation is audited. Owner: B1."""

from pema.clinic.audit.guard import AuditMissingError, install_audit_guard
from pema.clinic.audit.recorder import FORBIDDEN_DETAIL_KEYS, find_replay, record

install_audit_guard()

__all__ = [
    "FORBIDDEN_DETAIL_KEYS",
    "AuditMissingError",
    "find_replay",
    "install_audit_guard",
    "record",
]

"""What the retention job deletes, as data: one SQL predicate per group (new module, no TS source).

Every statement here is built from constants of this file (table names and predicates are literals, never
user input; the only values are bound parameters), which is why the f-strings below carry ``noqa: S608``.

Shape of a batch: pick up to ``:batch`` expired rows of ONE clinic with ``FOR UPDATE SKIP LOCKED`` (a second
runner or a writer holding a row is skipped, not waited for) and delete exactly those rows by ``ctid`` in the
same statement. One statement is one small transaction, so a run never holds a long lock and a crash loses at
most the batch in flight. The explicit ``clinic_id = :clinic_id`` (the installation id, the caller opens
``db.session()``) keeps the planner on the index prefix
of the clinic.

NOT touched, on purpose (each is a decision, not an omission):

* ``clinic.audit_log``: append-only by trigger and the evidence of who did what; no rule here names it.
* ``clinic.patient``, ``clinic.appointment``, ``clinic.consent``, ``clinic.treatment_*``, ``clinic.episode``,
  ``clinic.crm_*``: clinical and CRM records. Erasing a patient is a staff action, not a timer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import TextClause, text

from pema.retention.policy import RetentionPolicy, Scope


@dataclass(frozen=True)
class DeleteRule:
    """One group that is a plain "rows older than the cutoff" delete."""

    group: str
    """Key in the report and in the audit counters (snake_case)."""
    scope: Scope
    days: Callable[[RetentionPolicy], int]
    table: str
    where: str
    """Predicate on alias ``t``; the bound parameter is ``:cutoff`` (UTC, ``now - days``)."""
    delete_where: str | None = None
    """Stricter predicate for the real delete when the dry-run count must ignore a condition that the run
    itself satisfies first (an empty conversation is only deletable after its messages went)."""


_ALIAS_T = re.compile(r"(?<![A-Za-z0-9_])t[.]")


def count_sql(rule: DeleteRule) -> TextClause:
    return text(f"SELECT count(*) FROM {rule.table} t WHERE t.clinic_id = :clinic_id AND ({rule.where})")  # noqa: S608


def _batch_subselect(table: str, where: str) -> str:
    return (
        f"SELECT x.ctid FROM {table} x WHERE x.clinic_id = :clinic_id AND ({where}) "  # noqa: S608
        "LIMIT :batch FOR UPDATE OF x SKIP LOCKED"
    )


def delete_batch_sql(rule: DeleteRule) -> TextClause:
    where = _ALIAS_T.sub("x.", rule.delete_where or rule.where)
    return text(
        f"DELETE FROM {rule.table} t WHERE t.clinic_id = :clinic_id "  # noqa: S608
        f"AND t.ctid = ANY (ARRAY({_batch_subselect(rule.table, where)}))"
    )


# ----------------------------------------------------------------------------------------------- clinic
CLINIC_RULES: tuple[DeleteRule, ...] = (
    DeleteRule(
        "auth_sessions",
        Scope.CLINIC,
        lambda p: p.auth_session_days,
        "clinic.auth_session",
        "t.expires_at < :cutoff",
    ),
)

# ------------------------------------------------------------------------------------------------ audit
AUDIT_RUN = text("SELECT clinic.record_retention_run(:scope, CAST(:counts AS jsonb))")

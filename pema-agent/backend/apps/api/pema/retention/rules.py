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
* ``clinic.review_item``: an OPEN item (``pending`` or ``escalated``) is work somebody has not done; its
  conversation and messages are protected below. Decided items are not purged either (open item for the
  owner).
* ``agent.channel_update_seen``: purged every six hours by the webhook dedupe
  (``PostgresUpdateDedupe.purge``).
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


# ------------------------------------------------------------------------------------------------ agent
AGENT_RULES: tuple[DeleteRule, ...] = (
    DeleteRule(
        "memories",
        Scope.AGENT,
        lambda p: p.memory_days,
        "agent.memories",
        "t.created_at < :cutoff",
    ),
    # The raw model text, reasoning and tool output of a turn (SEC-06: tool output is stored unmasked in the
    # patient_channel profile). Same table the former daily ``prune_old_traces`` pruned.
    DeleteRule(
        "trace_steps",
        Scope.AGENT,
        lambda p: p.trace_days,
        "agent.usage_steps",
        "t.created_at < :cutoff",
    ),
    # The token ledger holds no conversation text; its steps go with it (ON DELETE CASCADE).
    DeleteRule(
        "usage",
        Scope.AGENT,
        lambda p: p.usage_days,
        "agent.usage",
        "t.created_at < :cutoff",
    ),
    # Scheduler delivery log. A row still ``running`` belongs to a live (or recoverable) worker: never.
    DeleteRule(
        "job_runs",
        Scope.AGENT,
        lambda p: p.job_run_days,
        "agent.job_runs",
        "t.status <> 'running' AND COALESCE(t.finished_at, t.started_at) < :cutoff",
    ),
    # A description of an image is as sensitive as the image: it goes on the same clock as the file.
    DeleteRule(
        "image_descriptions",
        Scope.AGENT,
        lambda p: p.media_days,
        "agent.image_descriptions",
        "t.created_at < :cutoff",
    ),
)

# ----------------------------------------------------------------------------------------------- clinic
CLINIC_RULES: tuple[DeleteRule, ...] = (
    # Messages of conversations that staff CLOSED at least ``message_days`` ago. The clock starts at the
    # closing (``updated_at`` of a closed conversation: a new inbound message reopens it first).
    DeleteRule(
        "messages",
        Scope.CLINIC,
        lambda p: p.message_days,
        "clinic.message",
        "EXISTS (SELECT 1 FROM clinic.conversation c WHERE c.clinic_id = t.clinic_id "
        "AND c.id = t.conversation_id AND c.status = 'closed' AND c.updated_at < :cutoff) "
        "AND NOT EXISTS (SELECT 1 FROM clinic.review_item r WHERE r.clinic_id = t.clinic_id "
        "AND r.conversation_id = t.conversation_id AND r.status IN ('pending', 'escalated')) "
        "AND NOT EXISTS (SELECT 1 FROM clinic.review_item r2 WHERE r2.clinic_id = t.clinic_id "
        "AND r2.id = t.review_item_id AND r2.status IN ('pending', 'escalated'))",
    ),
    # The empty shell afterwards. Any review item (open or decided) still points at its conversation by
    # foreign key, so a conversation with one stays.
    DeleteRule(
        "conversations",
        Scope.CLINIC,
        lambda p: p.message_days,
        "clinic.conversation",
        "t.status = 'closed' AND t.updated_at < :cutoff AND NOT EXISTS (SELECT 1 FROM clinic.review_item r "
        "WHERE r.clinic_id = t.clinic_id AND r.conversation_id = t.id)",
        delete_where="t.status = 'closed' AND t.updated_at < :cutoff AND NOT EXISTS (SELECT 1 FROM "
        "clinic.review_item r WHERE r.clinic_id = t.clinic_id AND r.conversation_id = t.id) "
        "AND NOT EXISTS (SELECT 1 FROM clinic.message m WHERE m.clinic_id = t.clinic_id "
        "AND m.conversation_id = t.id)",
    ),
    DeleteRule(
        "auth_sessions",
        Scope.CLINIC,
        lambda p: p.auth_session_days,
        "clinic.auth_session",
        "t.expires_at < :cutoff",
    ),
    # Only the hash of a code is stored; an expired or spent one has no further use.
    DeleteRule(
        "link_codes",
        Scope.CLINIC,
        lambda p: p.link_code_days,
        "clinic.identity_link_code",
        "t.expires_at < :cutoff OR t.used_at < :cutoff",
    ),
)

# ------------------------------------------------------------------------------- agent history (special)
HISTORY_COUNT = text(
    """
    SELECT count(*) AS n,
           COALESCE(sum(CASE WHEN jsonb_typeof(t.images) = 'array' THEN jsonb_array_length(t.images)
                             ELSE 0 END), 0) AS images
      FROM agent.history t WHERE t.clinic_id = :clinic_id AND t.created_at < :cutoff
    """
)
HISTORY_DELETE_BATCH = text(
    """
    DELETE FROM agent.history t
     WHERE t.clinic_id = :clinic_id
       AND t.ctid = ANY (ARRAY(SELECT x.ctid FROM agent.history x
                                WHERE x.clinic_id = :clinic_id AND x.created_at < :cutoff
                                LIMIT :batch FOR UPDATE OF x SKIP LOCKED))
    RETURNING t.images
    """
)
DESCRIPTIONS_OF_PATHS = text(
    "DELETE FROM agent.image_descriptions "
    "WHERE clinic_id = :clinic_id AND rel_path = ANY (CAST(:paths AS text[]))"
)

# The rolling summary is made FROM the history; once a thread has been idle past the cutoff and its history
# is gone, the summary would keep the deleted conversation alive. Same reset as ``wipe_thread_context``
# (summary, message count, epoch), but only for idle threads: an active thread's summary replaces the turns
# that ``HISTORY_MAX_MESSAGES_PER_THREAD`` already pruned and must stay.
_IDLE_THREAD = "x.last_message_at < :cutoff AND (x.summary <> '' OR x.message_count > 0)"
THREADS_COUNT = text(
    "SELECT count(*) FROM agent.threads x WHERE x.clinic_id = :clinic_id AND " + _IDLE_THREAD  # noqa: S608
)
THREADS_RESET_BATCH = text(
    f"""
    UPDATE agent.threads t
       SET summary = '', summary_covers_to_message_id = 0, message_count = 0,
           context_epoch = t.context_epoch + 1
     WHERE t.clinic_id = :clinic_id
       AND t.ctid = ANY (ARRAY(
            SELECT x.ctid FROM agent.threads x
             WHERE x.clinic_id = :clinic_id AND {_IDLE_THREAD}
               AND NOT EXISTS (SELECT 1 FROM agent.history h WHERE h.clinic_id = x.clinic_id
                               AND h.account_id = x.account_id AND h.thread_id = x.thread_id)
             LIMIT :batch FOR UPDATE OF x SKIP LOCKED))
    """  # noqa: S608
)

# ------------------------------------------------------------------------------------ audit and the door
AUDIT_RUN = text("SELECT clinic_agent.record_retention_run(:scope, CAST(:counts AS jsonb))")
PURGE_LINK_ATTEMPTS = text("SELECT clinic_agent.retention_purge_link_attempts(:cutoff, :batch, :dry_run)")

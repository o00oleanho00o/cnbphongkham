"""The invariants of the shared inbox, as SQL over the state a load or race run leaves behind. New module, no
zalo-agent original.

They are the acceptance of package O stated as queries (``PLAN-AI01-O`` section 6), so a run cannot pass by
checking only the calls it made itself. Each function takes the superuser engine of the throwaway database (a
test arranges and inspects raw state with it; the code under test never does) and the ids of the conversations
the run created (the seeded demo conversations were held before the history table existed and are not judged).

* ``one_holder``: a conversation has at most one holder, and the holder is an operator (an active user whose
  role is one of the assignable roles; reception and the accountant never hold a thread);
* ``history_chain``: the history of a conversation is a chain: each row's ``previous_user_id`` is the previous
  row's ``user_id``, and the current holder is the ``user_id`` of the last row;
* ``version_counts_changes``: ``assignment_version`` is 1 plus the number of history rows (every change of the
  holder bumps it once and writes one row, in one transaction);
* ``senders_held_the_thread``: every staff message was written by somebody who held the conversation at some
  point (a user who never held it never wrote to it; the approval of a review item is a decision of the
  approver and is exempt, as in the send lock), and every outbound message carries a sender
  (``sender_user_id`` for staff, ``sender_type`` ``ai_draft`` or ``system`` otherwise);
* ``no_credential_in_audit_or_outbox``: no audit row and no outbox payload carries a marker value planted in a
  ``*_enc`` column, and the outbox payloads hold only the fields of ``NotificationPayload``;
* ``takeover_has_a_reason``: a takeover row always has a reason (the table's own CHECK, read back).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema_contracts.ops import NotificationPayload

OPERATOR_ROLES = ("owner", "manager", "doctor", "cs_staff")
"""``ASSIGNABLE_ROLES`` of ``pema.clinic.actions.assignees`` as the strings of ``clinic.user_account.role``."""


@dataclass(frozen=True)
class Violation:
    """One broken invariant. ``detail`` holds ids and counts only."""

    rule: str
    conversation_id: UUID | None
    detail: str


def _ids(conversation_ids: Iterable[UUID]) -> list[UUID]:
    return list(dict.fromkeys(conversation_ids))


def one_holder(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id, c.assigned_user_id, u.role, u.active FROM clinic.conversation c "
                "LEFT JOIN clinic.user_account u ON u.id = c.assigned_user_id "
                "WHERE c.id = ANY(:ids) AND c.assigned_user_id IS NOT NULL"
            ),
            {"ids": ids},
        ).all()
    return [
        Violation("one_holder", row.id, f"holder role={row.role} active={row.active}")
        for row in rows
        if row.role not in OPERATOR_ROLES or not row.active
    ]


def history_chain(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    found: list[Violation] = []
    with engine.connect() as conn:
        history = conn.execute(
            text(
                "SELECT conversation_id, user_id, previous_user_id FROM clinic.conversation_assignment "
                'WHERE conversation_id = ANY(:ids) ORDER BY conversation_id, "at", id'
            ),
            {"ids": ids},
        ).all()
        holders = {
            row.id: row.assigned_user_id
            for row in conn.execute(
                text("SELECT id, assigned_user_id FROM clinic.conversation WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
        }
    last: dict[UUID, UUID | None] = {}
    seen: set[UUID] = set()
    for row in history:
        if row.conversation_id in seen and last[row.conversation_id] != row.previous_user_id:
            found.append(
                Violation("history_chain", row.conversation_id, "previous holder is not the last holder")
            )
        seen.add(row.conversation_id)
        last[row.conversation_id] = row.user_id
    for conversation_id, holder in holders.items():
        expected = last.get(conversation_id)
        if holder != expected:
            found.append(
                Violation("history_chain", conversation_id, "the holder is not the last history row")
            )
    return found


def version_counts_changes(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.id, c.assignment_version, count(h.id) AS changes FROM clinic.conversation c "
                "LEFT JOIN clinic.conversation_assignment h ON h.conversation_id = c.id "
                "WHERE c.id = ANY(:ids) GROUP BY c.id, c.assignment_version"
            ),
            {"ids": ids},
        ).all()
    return [
        Violation("version_counts_changes", row.id, f"version={row.assignment_version} changes={row.changes}")
        for row in rows
        if row.assignment_version != 1 + row.changes
    ]


def senders_held_the_thread(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    with engine.connect() as conn:
        unsigned = conn.execute(
            text(
                "SELECT id, conversation_id, sender_type FROM clinic.message WHERE conversation_id = ANY(:ids) "
                "AND direction = 'outbound' AND NOT ((sender_type = 'staff' AND sender_user_id IS NOT NULL) "
                "OR sender_type IN ('ai_draft', 'system'))"
            ),
            {"ids": ids},
        ).all()
        strangers = conn.execute(
            text(
                "SELECT m.id, m.conversation_id FROM clinic.message m WHERE m.conversation_id = ANY(:ids) "
                "AND m.direction = 'outbound' AND m.sender_type = 'staff' AND m.review_item_id IS NULL AND NOT EXISTS ("
                "SELECT 1 FROM clinic.conversation_assignment h WHERE h.conversation_id = m.conversation_id "
                "AND h.user_id = m.sender_user_id)"
            ),
            {"ids": ids},
        ).all()
    return [
        *(
            Violation("sender_signed", row.conversation_id, f"message without a sender ({row.sender_type})")
            for row in unsigned
        ),
        *(
            Violation("senders_held_the_thread", row.conversation_id, "sender never held the thread")
            for row in strangers
        ),
    ]


def takeover_has_a_reason(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT conversation_id FROM clinic.conversation_assignment WHERE conversation_id = ANY(:ids) "
                "AND kind = 'takeover' AND (reason IS NULL OR btrim(reason) = '')"
            ),
            {"ids": ids},
        ).all()
    return [
        Violation("takeover_has_a_reason", row.conversation_id, "takeover without a reason") for row in rows
    ]


def payload_fields_only(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    """Every outbox payload of the conversations has no key outside ``NotificationPayload``."""
    allowed = set(NotificationPayload.model_fields)
    ids = _ids(conversation_ids)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, conversation_id, payload FROM clinic.notification_outbox WHERE conversation_id = ANY(:ids)"
            ),
            {"ids": ids},
        ).all()
    found: list[Violation] = []
    for row in rows:
        raw: Any = row.payload
        payload = cast(dict[str, Any], json.loads(raw) if isinstance(raw, str) else raw)
        extra = sorted(set(payload) - allowed)
        if extra:
            found.append(
                Violation("payload_fields_only", row.conversation_id, f"keys outside the contract: {extra}")
            )
    return found


def no_marker_in_audit_or_outbox(engine: Engine, markers: Sequence[str]) -> list[Violation]:
    """None of the planted marker values appears in the audit log or in any outbox payload."""
    with engine.connect() as conn:
        audit = "".join(
            row.details or ""
            for row in conn.execute(text("SELECT details::text AS details FROM clinic.audit_log"))
        )
        outbox = "".join(
            row.payload or ""
            for row in conn.execute(text("SELECT payload::text AS payload FROM clinic.notification_outbox"))
        )
    return [
        Violation("no_marker_in_audit_or_outbox", None, f"marker found in {where}")
        for marker in markers
        for where, blob in (("audit", audit), ("outbox", outbox))
        if marker in blob
    ]


def all_invariants(engine: Engine, conversation_ids: Iterable[UUID]) -> list[Violation]:
    ids = _ids(conversation_ids)
    return [
        *one_holder(engine, ids),
        *history_chain(engine, ids),
        *version_counts_changes(engine, ids),
        *senders_held_the_thread(engine, ids),
        *takeover_has_a_reason(engine, ids),
        *payload_fields_only(engine, ids),
    ]

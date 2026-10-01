"""Test support of the retention job: synthetic rows with an explicit age (not imported by production code).

Same pattern as ``pema.conversation.pg_testing``. ``Seed`` inserts as the SUPERUSER of the throwaway database
(bypassing RLS) so a test can place rows of any age in any clinic; the code under test always runs as a runtime
role (``be_app`` or ``agent_worker``).
"""

# ruff: noqa: E501  (long SQL literals of synthetic rows)

from __future__ import annotations

import json
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.conversation.pg_testing import ClinicEnv


class Seed:
    """Synthetic rows with an explicit age in days (``age=40`` = created 40 days ago), inserted as superuser."""

    def __init__(self, env: ClinicEnv) -> None:
        self._env = env

    def sql(self, statement: str, **params: Any) -> Any:
        with self._env.server.admin_engine.begin() as conn:
            result = conn.execute(text(statement), params)
            return result.scalar() if result.returns_rows else None

    def count(self, table: str, clinic: UUID, where: str = "true") -> int:
        return int(
            self.sql(f"SELECT count(*) FROM {table} WHERE clinic_id = :c AND ({where})", c=clinic)  # noqa: S608
        )

    def new_clinic(self) -> UUID:
        return self._env.add_clinic(uuid.uuid4(), ("acc-1",))

    # ----------------------------------------------------------------------------------------------- agent
    def history(
        self,
        clinic: UUID,
        age: int,
        *,
        images: list[str] | None = None,
        account: str = "acc-1",
        thread: str = "t-1",
        n: int = 1,
    ) -> None:
        for i in range(n):
            self.sql(
                "INSERT INTO agent.history (clinic_id, account_id, thread_id, role, content, images, created_at) "
                "VALUES (:c, :a, :t, 'user', :content, CAST(:images AS jsonb), now() - make_interval(days => :age)) "
                "RETURNING id",
                c=clinic,
                a=account,
                t=thread,
                content=f"synthetic message {i}",
                images=json.dumps(images) if images else None,
                age=age,
            )

    def history_bulk(self, clinic: UUID, age: int, n: int) -> None:
        self.sql(
            "INSERT INTO agent.history (clinic_id, account_id, thread_id, role, content, created_at) "
            "SELECT :c, 'acc-1', 't-bulk', 'user', 'synthetic ' || g, now() - make_interval(days => :age) "
            "FROM generate_series(1, :n) g RETURNING 1",
            c=clinic,
            age=age,
            n=n,
        )

    def thread(
        self, clinic: UUID, thread: str, *, last_message_age: int, summary: str = "synthetic summary"
    ) -> None:
        self.sql(
            "INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type, display_name, summary, "
            "summary_covers_to_message_id, message_count, last_message_at) "
            "VALUES (:c, 'acc-1', :t, 0, 'Synthetic', :s, 5, 5, now() - make_interval(days => :age)) RETURNING 1",
            c=clinic,
            t=thread,
            s=summary,
            age=last_message_age,
        )

    def memory(self, clinic: UUID, age: int) -> None:
        self.sql(
            "INSERT INTO agent.memories (clinic_id, account_id, subject_id, content, learned_in_thread_id, created_at) "
            "VALUES (:c, 'acc-1', 'subject-1', 'synthetic fact', 't-1', now() - make_interval(days => :age)) "
            "RETURNING 1",
            c=clinic,
            age=age,
        )

    def usage_turn(self, clinic: UUID, age: int, steps: int = 2) -> int:
        turn_id = int(
            self.sql(
                "INSERT INTO agent.usage (clinic_id, account_id, thread_id, created_at) "
                "VALUES (:c, 'acc-1', 't-1', now() - make_interval(days => :age)) RETURNING id",
                c=clinic,
                age=age,
            )
        )
        for step in range(steps):
            self.sql(
                "INSERT INTO agent.usage_steps (clinic_id, turn_id, step_number, text, created_at) "
                "VALUES (:c, :turn, :n, 'synthetic', now() - make_interval(days => :age)) RETURNING 1",
                c=clinic,
                turn=turn_id,
                n=step,
                age=age,
            )
        return turn_id

    def job_run(self, clinic: UUID, job: str, age: int, status: str = "ok") -> None:
        self.sql(
            "INSERT INTO agent.jobs (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, "
            "schedule_kind, max_runs) VALUES (:c, :j, 'acc-1', 't-1', 0, 'job', 'message', 'x', 'once', 1) "
            "ON CONFLICT DO NOTHING RETURNING 1",
            c=clinic,
            j=job,
        )
        self.sql(
            "INSERT INTO agent.job_runs (clinic_id, job_id, status, started_at, finished_at) "
            "VALUES (:c, :j, :s, now() - make_interval(days => :age), "
            "CASE WHEN :s = 'running' THEN NULL ELSE now() - make_interval(days => :age) END) RETURNING 1",
            c=clinic,
            j=job,
            s=status,
            age=age,
        )

    def image_description(self, clinic: UUID, rel_path: str, age: int) -> None:
        self.sql(
            "INSERT INTO agent.image_descriptions (clinic_id, rel_path, description, created_at) "
            "VALUES (:c, :p, 'synthetic description', now() - make_interval(days => :age)) RETURNING 1",
            c=clinic,
            p=rel_path,
            age=age,
        )

    # ---------------------------------------------------------------------------------------------- clinic
    def user(self, clinic: UUID) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.user_account (clinic_id, email, display_name, role) "
                    "VALUES (:c, :e, 'Synthetic staff', 'cs_staff') RETURNING id",
                    c=clinic,
                    e=f"staff-{uuid.uuid4().hex[:8]}@example.test",
                )
            )
        )

    def patient(self, clinic: UUID) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, :code, 'Synthetic Patient') "
                    "RETURNING id",
                    c=clinic,
                    code=f"BN-{uuid.uuid4().hex[:8]}",
                )
            )
        )

    def conversation(self, clinic: UUID, status: str, age: int) -> UUID:
        """``age`` = days since the last update (for a closed conversation: since it was closed)."""
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, status, updated_at) "
                    "VALUES (:c, 'zalo_bot', :ref, :s, now() - make_interval(days => :age)) RETURNING id",
                    c=clinic,
                    ref=f"thread-{uuid.uuid4().hex[:10]}",
                    s=status,
                    age=age,
                )
            )
        )

    def message(self, clinic: UUID, conversation: UUID, *, review_item: UUID | None = None) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.message (clinic_id, conversation_id, channel, direction, sender_type, body, "
                    "review_item_id) VALUES (:c, :conv, 'zalo_bot', 'inbound', 'patient', 'synthetic body', :r) "
                    "RETURNING id",
                    c=clinic,
                    conv=conversation,
                    r=review_item,
                )
            )
        )

    def review_item(self, clinic: UUID, conversation: UUID, status: str) -> UUID:
        return UUID(
            str(
                self.sql(
                    "INSERT INTO clinic.review_item (clinic_id, kind, status, conversation_id, draft_text) "
                    "VALUES (:c, 'reply_draft', :s, :conv, 'synthetic draft') RETURNING id",
                    c=clinic,
                    s=status,
                    conv=conversation,
                )
            )
        )

    def auth_session(self, clinic: UUID, user: UUID, expired_days_ago: int) -> None:
        """A negative ``expired_days_ago`` is a session that is still valid."""
        self.sql(
            "INSERT INTO clinic.auth_session (clinic_id, user_id, password_fingerprint, expires_at) "
            "VALUES (:c, :u, 'fp', now() - make_interval(days => :d)) RETURNING 1",
            c=clinic,
            u=user,
            d=expired_days_ago,
        )

    def link_code(
        self,
        clinic: UUID,
        patient: UUID,
        user: UUID,
        *,
        expired_days_ago: int,
        used_days_ago: int | None = None,
    ) -> None:
        self.sql(
            "INSERT INTO clinic.identity_link_code (clinic_id, patient_id, code_hash, issued_by, expires_at, used_at) "
            "VALUES (:c, :p, :h, :u, now() - make_interval(days => :d), "
            "CASE WHEN CAST(:used AS integer) IS NULL THEN NULL "
            "ELSE now() - make_interval(days => CAST(:used AS integer)) END) RETURNING 1",
            c=clinic,
            p=patient,
            h=uuid.uuid4().hex + uuid.uuid4().hex,
            u=user,
            d=expired_days_ago,
            used=used_days_ago,
        )

    def link_attempt(self, clinic: UUID, age_days: int) -> None:
        self.sql(
            "INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded, "
            "attempted_at) VALUES (:c, 'zalo_bot', 'ext-1', 'code', false, now() - make_interval(days => :d)) "
            "RETURNING 1",
            c=clinic,
            d=age_days,
        )

    def audit(self, clinic: UUID, age: int) -> None:
        self.sql(
            "INSERT INTO clinic.audit_log (clinic_id, occurred_at, actor_type, action, entity_type) "
            "VALUES (:c, now() - make_interval(days => :age), 'system', 'synthetic.event', 'synthetic') RETURNING 1",
            c=clinic,
            age=age,
        )

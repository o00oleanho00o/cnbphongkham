"""scheduler runtime: liveness columns of ``agent.job_runs`` for several scheduler workers (package S).

zalo-agent ran ONE process, so at boot every ``scheduled_job_runs`` row still ``running`` could only belong to
the previous incarnation of that process, and a ``once`` job whose ``next_run_at`` was NULL (claimed before
dispatch) could only be an orphan. With several workers (and several clinics) neither is true any more: a live
worker may be in the middle of a long agent turn. The fix keeps the original meaning and adds the one fact
that was implicit: WHO is running a row and WHEN it last proved it is alive.

* ``worker_id``: the worker that opened the row (``SchedulerDeps.worker_id``).
* ``heartbeat_at``: refreshed every few seconds by the run itself while it dispatches. A ``running`` row whose
  heartbeat is older than the stale window belongs to a dead worker: recovery marks it ``interrupted`` and
  revives the ``once`` job it had claimed (``scheduler_loop.recover_clinic``).

No new table, no new grant: ``agent_worker`` and ``be_app`` already have DML on ``agent.*`` (0002) and RLS on
``clinic_id`` stays as it is.

Revision ID: s_0004_scheduler_runtime
Revises: 0003_clinic_agent_access
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s_0004_scheduler_runtime"
down_revision = "0003_clinic_agent_access"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("ALTER TABLE agent.job_runs ADD COLUMN worker_id text")
    _sql("ALTER TABLE agent.job_runs ADD COLUMN heartbeat_at timestamptz NOT NULL DEFAULT now()")
    _sql(
        "CREATE INDEX job_runs_running_idx ON agent.job_runs (clinic_id, heartbeat_at) "
        "WHERE status = 'running'"
    )


def downgrade() -> None:
    _sql("DROP INDEX IF EXISTS agent.job_runs_running_idx")
    _sql("ALTER TABLE agent.job_runs DROP COLUMN IF EXISTS heartbeat_at")
    _sql("ALTER TABLE agent.job_runs DROP COLUMN IF EXISTS worker_id")

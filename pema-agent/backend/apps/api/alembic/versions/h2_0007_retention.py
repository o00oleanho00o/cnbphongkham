"""H2: data retention. Indexes for the age scans, one audit door and one narrow purge door (new, no TS source).

The retention job (``pema.retention``) deletes expired rows in small batches, per clinic, under row level
security. Two processes run it and neither gets a wider right on ``clinic.*`` than it had:

* the API process (``be_app``) runs the ``clinic`` scope: messages of closed conversations, expired dashboard
  sessions, expired identity-link codes. ``be_app`` already has DELETE on those tables (0001, b1_0004, p0001);
* the worker process (``agent_worker``, no privilege on ``clinic.*``) runs the ``agent`` scope on ``agent.*``
  (it already has DML there) and the local media files.

What this revision adds:

* ``clinic_agent.record_retention_run(scope, counts)``: SECURITY DEFINER, executable by BOTH runtime roles. It
  writes ONE summary row in ``clinic.audit_log`` (actor ``system``, action ``retention.run``). The worker has
  no INSERT on ``clinic.audit_log``, so this is its only way to leave the row, and the function cannot carry
  PII: ``counts`` must be a flat JSON object of non-negative integers under short snake_case keys.
* ``clinic_agent.retention_purge_link_attempts(cutoff, limit, dry_run)``: SECURITY DEFINER, executable by
  ``be_app`` ONLY. ``clinic.identity_link_attempt`` is evidence (p0001 revoked UPDATE and DELETE from
  ``be_app`` on purpose), so no role may rewrite it; ageing rows out is the one exception, in a door that can
  do nothing else: it refuses a cutoff younger than one hour (the rate limiter of the link functions counts
  failures of the last hour; deleting them would switch the limiter off) and it only touches the clinic of
  the current transaction.
* indexes ``(clinic_id, <age column>)`` so the scans of the job do not read a whole table.

Both functions pin ``search_path`` with ``pg_temp`` last (the rule of g_0006 for every definer function).

``clinic.audit_log`` is NOT purged by anything here or in the job: it is append-only by trigger and it is the
evidence of who did what; keeping it is not a retention decision the job may take.

Revision ID: h2_0007_retention
Revises: g_0006_definer_search_path
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h2_0007_retention"
down_revision = "g_0006_definer_search_path"
branch_labels = None
depends_on = None

INDEXES = (
    "CREATE INDEX IF NOT EXISTS history_age_idx ON agent.history (clinic_id, created_at)",
    "CREATE INDEX IF NOT EXISTS memories_age_idx ON agent.memories (clinic_id, created_at)",
    "CREATE INDEX IF NOT EXISTS usage_age_idx ON agent.usage (clinic_id, created_at)",
    "CREATE INDEX IF NOT EXISTS usage_steps_clinic_age_idx ON agent.usage_steps (clinic_id, created_at)",
    "CREATE INDEX IF NOT EXISTS job_runs_age_idx ON agent.job_runs (clinic_id, started_at)",
    "CREATE INDEX IF NOT EXISTS image_descriptions_age_idx ON agent.image_descriptions (clinic_id, created_at)",
    "CREATE INDEX IF NOT EXISTS identity_link_code_expiry_idx ON clinic.identity_link_code (clinic_id, expires_at)",
    "CREATE INDEX IF NOT EXISTS conversation_closed_age_idx ON clinic.conversation (clinic_id, updated_at) "
    "WHERE status = 'closed'",
)
INDEX_NAMES = (
    "agent.history_age_idx",
    "agent.memories_age_idx",
    "agent.usage_age_idx",
    "agent.usage_steps_clinic_age_idx",
    "agent.job_runs_age_idx",
    "agent.image_descriptions_age_idx",
    "clinic.identity_link_code_expiry_idx",
    "clinic.conversation_closed_age_idx",
)
RUN_FN = "clinic_agent.record_retention_run(text, jsonb)"
PURGE_FN = "clinic_agent.retention_purge_link_attempts(timestamptz, integer, boolean)"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    for statement in INDEXES:
        _sql(statement)

    _sql("""
        CREATE FUNCTION clinic_agent.record_retention_run(p_scope text, p_counts jsonb)
        RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx, pg_temp AS $$
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_id bigint;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_scope NOT IN ('agent', 'clinic') THEN RAISE EXCEPTION 'bad retention scope'; END IF;
            IF p_counts IS NULL OR jsonb_typeof(p_counts) <> 'object' THEN
                RAISE EXCEPTION 'counts must be a JSON object';
            END IF;
            IF (SELECT count(*) FROM jsonb_object_keys(p_counts)) > 40 THEN
                RAISE EXCEPTION 'too many counters';
            END IF;
            -- Counters only: short snake_case keys, non-negative integers. No free text can get in.
            IF EXISTS (SELECT 1 FROM jsonb_each(p_counts) e
                        WHERE e.key !~ '^[a-z][a-z_]{0,39}$'
                           OR jsonb_typeof(e.value) <> 'number'
                           OR e.value::text !~ '^[0-9]{1,12}$') THEN
                RAISE EXCEPTION 'counts must map snake_case names to non-negative integers';
            END IF;
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'system', 'retention.run', 'retention', p_scope,
                    jsonb_build_object('scope', p_scope, 'deleted', p_counts))
            RETURNING id INTO v_id;
            RETURN v_id;
        END $$""")

    _sql("""
        CREATE FUNCTION clinic_agent.retention_purge_link_attempts(
            p_cutoff timestamptz, p_limit integer, p_dry_run boolean)
        RETURNS integer
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, ctx, pg_temp AS $$
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_n integer;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            -- The failure limiter of the link functions looks one hour back: never delete inside it.
            IF p_cutoff IS NULL OR p_cutoff > now() - interval '1 hour' THEN
                RAISE EXCEPTION 'cutoff must be older than one hour';
            END IF;
            IF p_dry_run THEN
                SELECT count(*)::integer INTO v_n FROM clinic.identity_link_attempt a
                 WHERE a.clinic_id = v_clinic AND a.attempted_at < p_cutoff;
                RETURN v_n;
            END IF;
            IF p_limit IS NULL OR p_limit < 1 OR p_limit > 10000 THEN
                RAISE EXCEPTION 'limit must be between 1 and 10000';
            END IF;
            WITH doomed AS (
                SELECT a.id FROM clinic.identity_link_attempt a
                 WHERE a.clinic_id = v_clinic AND a.attempted_at < p_cutoff
                 ORDER BY a.id LIMIT p_limit FOR UPDATE SKIP LOCKED)
            DELETE FROM clinic.identity_link_attempt t USING doomed WHERE t.id = doomed.id;
            GET DIAGNOSTICS v_n = ROW_COUNT;
            RETURN v_n;
        END $$""")

    _sql(f"REVOKE ALL ON FUNCTION {RUN_FN} FROM PUBLIC")
    _sql(f"GRANT EXECUTE ON FUNCTION {RUN_FN} TO agent_worker, be_app")
    _sql(f"REVOKE ALL ON FUNCTION {PURGE_FN} FROM PUBLIC")
    _sql(f"GRANT EXECUTE ON FUNCTION {PURGE_FN} TO be_app")


def downgrade() -> None:
    _sql(f"DROP FUNCTION IF EXISTS {PURGE_FN}")
    _sql(f"DROP FUNCTION IF EXISTS {RUN_FN}")
    for name in INDEX_NAMES:
        _sql(f"DROP INDEX IF EXISTS {name}")

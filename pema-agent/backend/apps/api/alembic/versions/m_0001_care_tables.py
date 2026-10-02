"""per-patient care agent tables (package M, step M1): ``agent.*`` care tables and three ``clinic.*`` staff tables.

Source: ``docs/PLAN-AI01-M.md`` section 10. Single tenant (revision ``st_0009_single_tenant``): there is NO
row level security and no clinic context any more, so no policy is created here. Every table keeps the
``clinic_id`` column (the fixed installation id, ``CONTRACTS-AI01.md`` 10.8) with a foreign key to
``clinic.clinic``, ``created_at``/``updated_at`` (trigger) and ``version`` (optimistic locking, ARCH-PB01).

``agent`` schema (both runtime roles already get DML through the default privileges of ``0002_agent_schema``;
the GRANTs are repeated here so the migration does not depend on who owns the defaults):

* ``care_agents``: one row per patient (``UNIQUE (patient_id)``), the 1-to-1 pairing. ``autonomy_levels`` maps an
  action type to ``L0``/``L1``/``L2`` (an empty object means L0 everywhere), ``autonomy_override`` is NULL or
  ``{"level", "until"}`` (a time-boxed cap set when a staff member hands the conversation back),
  ``trust_scores`` and ``preferences`` are free jsonb objects. ``profile`` is the policy profile and is
  always ``patient_channel`` for patients (PLAN-M 11.1).
* ``care_memory``: short facts about ONE patient, from ``patient``/``staff``/``doctor_edit``. It has no column for
  clinical record data and the ``fact`` text is length-capped; PII is masked before anything is written.
* ``conversation_control``: the state machine row of a patient (AUTO, HANDOFF_ROUTING, STAFF). ``auto_release_after``
  is NULL by default (only staff return a conversation to AUTO).
* ``handoff_requests``: one routing round. ``candidates`` is the jsonb list of candidate staff, ``current_idx`` the
  position in it; ``outcome`` is NULL while the request is open, at most one open request per patient.
* ``tasks``: work given to a specialist agent (depth 1: ``parent_id`` points at a task of the care agent).
* ``actions_log``: what the care agent did (auto_sent, reviewed, paused) and the doctor's edit diff.
* ``skills``: named instruction + classifier configuration (``handoff`` first).

``clinic`` schema: ``staff_profiles`` (skills, shift, capacity, languages per user), ``patient_ownership`` (CS owner
and treating doctor per patient), ``on_call_contacts`` (the 24/7 Zalo number, ``is_fixture`` marks test data).
Only ``be_app`` gets DML on them.

Deviation from the recipe, on purpose: ``agent_worker`` must still have NO privilege on schema ``clinic``
(``test_agent_worker_has_no_privilege_on_clinic_schema``, SECURITY-REVIEW). The "worker may read these three
tables" requirement is therefore met the way the rest of the clinic is exposed to it: three views in
``clinic_agent`` (``staff_profile``, ``patient_ownership``, ``on_call_contact``), ``security_barrier`` and
filtered by ``ctx.the_clinic_id()``, SELECT only. The worker cannot read or write ``clinic.*`` directly.

Upgrade also pairs every patient that already exists with a care agent and copies the owner and doctor of
``clinic.patient`` into ``clinic.patient_ownership`` (idempotent ``ON CONFLICT DO NOTHING``). New patients are
paired by ``pema.care.pairing`` (see ``PatientCreatedHook`` in ``pema.care.ports``).

Revision ID: m_0001_care_tables
Revises: st_0009_single_tenant
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m_0001_care_tables"
down_revision = "st_0009_single_tenant"
branch_labels = None
depends_on = None

STAFF_ROLES = ("owner", "manager", "doctor", "cs_staff", "reception")
POLICY_PROFILES = ("staff_assistant", "patient_channel")
AGENT_TABLES = (
    "care_agents",
    "care_memory",
    "conversation_control",
    "handoff_requests",
    "tasks",
    "actions_log",
    "skills",
)
CLINIC_TABLES = ("staff_profiles", "patient_ownership", "on_call_contacts")
VIEWS = ("staff_profile", "patient_ownership", "on_call_contact")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # ---------------------------------------------------------------- agent.care_agents
    _sql(f"""
        CREATE TABLE agent.care_agents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            profile text NOT NULL DEFAULT 'patient_channel' CHECK (profile IN ({_q(POLICY_PROFILES)})),
            autonomy_levels jsonb NOT NULL DEFAULT '{{}}'::jsonb
                CHECK (jsonb_typeof(autonomy_levels) = 'object'),
            autonomy_override jsonb
                CHECK (autonomy_override IS NULL OR (
                    jsonb_typeof(autonomy_override) = 'object'
                    AND autonomy_override ? 'level' AND autonomy_override ? 'until'
                    AND autonomy_override ->> 'level' IN ('L0', 'L1', 'L2'))),
            trust_scores jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(trust_scores) = 'object'),
            preferences jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(preferences) = 'object'),
            last_tick_at timestamptz,
            paused boolean NOT NULL DEFAULT false,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (patient_id),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id) ON DELETE CASCADE
        )""")

    # ---------------------------------------------------------------- agent.care_memory
    _sql("""
        CREATE TABLE agent.care_memory (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            care_agent_id uuid NOT NULL,
            fact text NOT NULL CHECK (length(fact) BETWEEN 1 AND 500),
            source text NOT NULL CHECK (source IN ('patient', 'staff', 'doctor_edit')),
            valid_until timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents (clinic_id, id)
                ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX care_memory_agent_idx ON agent.care_memory (care_agent_id, valid_until)")

    # ---------------------------------------------------------------- agent.conversation_control
    _sql("""
        CREATE TABLE agent.conversation_control (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            state text NOT NULL DEFAULT 'AUTO' CHECK (state IN ('AUTO', 'HANDOFF_ROUTING', 'STAFF')),
            since timestamptz NOT NULL DEFAULT now(),
            staff_owner uuid,
            release_note text,
            auto_release_after interval CHECK (auto_release_after IS NULL OR auto_release_after > interval '0'),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (patient_id),
            CHECK (state <> 'STAFF' OR staff_owner IS NOT NULL),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, staff_owner) REFERENCES clinic.user_account (clinic_id, id)
        )""")

    # ---------------------------------------------------------------- agent.handoff_requests
    _sql("""
        CREATE TABLE agent.handoff_requests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            reason text NOT NULL,
            depth text NOT NULL CHECK (depth IN ('D1', 'D2', 'D3', 'D4', 'D5')),
            confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
            required_skill text,
            urgency text NOT NULL DEFAULT 'normal' CHECK (urgency IN ('urgent', 'normal')),
            candidates jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(candidates) = 'array'),
            current_idx integer NOT NULL DEFAULT 0 CHECK (current_idx >= 0),
            current_notified_at timestamptz,
            accepted_by uuid,
            outcome text CHECK (outcome IN ('accepted', 'exhausted_to_oncall', 'cancelled')),
            resolved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (accepted_by IS NULL OR outcome IS NOT DISTINCT FROM 'accepted'),
            CHECK (outcome IS DISTINCT FROM 'accepted' OR accepted_by IS NOT NULL),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, accepted_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX handoff_requests_patient_idx ON agent.handoff_requests (patient_id, created_at DESC)")
    _sql(
        "CREATE UNIQUE INDEX handoff_requests_one_open_idx ON agent.handoff_requests (patient_id) "
        "WHERE outcome IS NULL"
    )

    # ---------------------------------------------------------------- agent.tasks
    _sql("""
        CREATE TABLE agent.tasks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            parent_id uuid,
            care_agent_id uuid NOT NULL,
            agent_id text NOT NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed', 'needs_human', 'cancelled')),
            input jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(input) = 'object'),
            result jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
            tokens integer NOT NULL DEFAULT 0 CHECK (tokens >= 0),
            cost numeric(12, 6) NOT NULL DEFAULT 0 CHECK (cost >= 0),
            started_at timestamptz,
            finished_at timestamptz,
            deadline_at timestamptz,
            error text,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents (clinic_id, id)
                ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, parent_id) REFERENCES agent.tasks (clinic_id, id) ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX tasks_agent_status_idx ON agent.tasks (care_agent_id, status)")
    _sql("CREATE INDEX tasks_parent_idx ON agent.tasks (parent_id) WHERE parent_id IS NOT NULL")

    # ---------------------------------------------------------------- agent.actions_log
    _sql("""
        CREATE TABLE agent.actions_log (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            care_agent_id uuid NOT NULL,
            action_type text NOT NULL,
            depth text CHECK (depth IN ('D1', 'D2', 'D3', 'D4', 'D5')),
            disposition text NOT NULL CHECK (disposition IN ('auto_sent', 'reviewed', 'paused')),
            reviewer_edit_diff jsonb,
            at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (clinic_id, care_agent_id) REFERENCES agent.care_agents (clinic_id, id)
                ON DELETE CASCADE
        )""")
    _sql("CREATE INDEX actions_log_agent_idx ON agent.actions_log (care_agent_id, at DESC)")

    # ---------------------------------------------------------------- agent.skills
    _sql(f"""
        CREATE TABLE agent.skills (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            name text NOT NULL CHECK (name ~ '^[a-z0-9][a-z0-9_-]*$'),
            instruction text NOT NULL,
            classifier_config jsonb NOT NULL DEFAULT '{{}}'::jsonb
                CHECK (jsonb_typeof(classifier_config) = 'object'),
            enabled_for_profiles text[] NOT NULL DEFAULT '{{}}'::text[]
                CHECK (enabled_for_profiles <@ ARRAY[{_q(POLICY_PROFILES)}]::text[]),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, name)
        )""")

    for table in AGENT_TABLES:
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON agent.{table} "
            "FOR EACH ROW EXECUTE FUNCTION agent.touch_updated_at()"
        )
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON agent.{table} TO be_app, agent_worker")
    _sql("GRANT USAGE ON ALL SEQUENCES IN SCHEMA agent TO be_app, agent_worker")

    # ---------------------------------------------------------------- clinic.staff_profiles
    _sql(f"""
        CREATE TABLE clinic.staff_profiles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            user_id uuid NOT NULL,
            role text NOT NULL CHECK (role IN ({_q(STAFF_ROLES)})),
            skills text[] NOT NULL DEFAULT '{{}}'::text[],
            shift jsonb NOT NULL DEFAULT '{{}}'::jsonb CHECK (jsonb_typeof(shift) = 'object'),
            capacity integer NOT NULL DEFAULT 5 CHECK (capacity >= 0),
            languages text[] NOT NULL DEFAULT ARRAY['vi']::text[],
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id),
            FOREIGN KEY (clinic_id, user_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")

    # ---------------------------------------------------------------- clinic.patient_ownership
    _sql("""
        CREATE TABLE clinic.patient_ownership (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            cs_owner uuid,
            doctor uuid,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (patient_id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id) ON DELETE CASCADE,
            FOREIGN KEY (clinic_id, cs_owner) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor) REFERENCES clinic.user_account (clinic_id, id)
        )""")

    # ---------------------------------------------------------------- clinic.on_call_contacts
    _sql("""
        CREATE TABLE clinic.on_call_contacts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            zalo_number text NOT NULL CHECK (zalo_number ~ '^\\+?[0-9]{8,15}$'),
            owner text NOT NULL CHECK (length(owner) BETWEEN 1 AND 120),
            valid_from timestamptz NOT NULL DEFAULT now(),
            valid_to timestamptz,
            active boolean NOT NULL DEFAULT true,
            is_fixture boolean NOT NULL DEFAULT false,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (valid_to IS NULL OR valid_to > valid_from)
        )""")
    _sql(
        "CREATE INDEX on_call_contacts_active_idx ON clinic.on_call_contacts (clinic_id, active, valid_from)"
    )

    for table in CLINIC_TABLES:
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")

    # ---------------------------------------------------------------- the worker's read door
    _sql("""
        CREATE VIEW clinic_agent.staff_profile WITH (security_barrier = true) AS
        SELECT s.id, s.clinic_id, s.user_id, s.role, s.skills, s.shift, s.capacity, s.languages
          FROM clinic.staff_profiles s
         WHERE s.clinic_id = ctx.the_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.patient_ownership WITH (security_barrier = true) AS
        SELECT o.id, o.clinic_id, o.patient_id, o.cs_owner, o.doctor
          FROM clinic.patient_ownership o
         WHERE o.clinic_id = ctx.the_clinic_id()""")
    _sql("""
        CREATE VIEW clinic_agent.on_call_contact WITH (security_barrier = true) AS
        SELECT c.id, c.clinic_id, c.zalo_number, c.owner, c.valid_from, c.valid_to, c.active, c.is_fixture
          FROM clinic.on_call_contacts c
         WHERE c.clinic_id = ctx.the_clinic_id()""")
    for view in VIEWS:
        _sql(f"REVOKE ALL ON clinic_agent.{view} FROM PUBLIC")
        _sql(f"GRANT SELECT ON clinic_agent.{view} TO agent_worker")

    # ---------------------------------------------------------------- existing patients
    _sql("""
        INSERT INTO agent.care_agents (clinic_id, patient_id)
        SELECT p.clinic_id, p.id FROM clinic.patient p
        ON CONFLICT (patient_id) DO NOTHING""")
    _sql("""
        INSERT INTO clinic.patient_ownership (clinic_id, patient_id, cs_owner, doctor)
        SELECT p.clinic_id, p.id, p.cs_owner_id, p.doctor_id FROM clinic.patient p
        ON CONFLICT (patient_id) DO NOTHING""")


def downgrade() -> None:
    for view in VIEWS:
        _sql(f"DROP VIEW IF EXISTS clinic_agent.{view}")
    for table in reversed(CLINIC_TABLES):
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    for table in reversed(AGENT_TABLES):
        _sql(f"DROP TABLE IF EXISTS agent.{table}")

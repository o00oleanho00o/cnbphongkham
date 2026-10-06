"""service catalog, rooms and protocols (package U, step U4).

Source: ``prototype/shared/operations-data.js`` (``services``, ``rooms``, ``blocks``, ``updateService``,
``block``), ``prototype/finance_server.py`` (``seed`` services with ``price``, ``rate``, ``basis``, ``version``;
``mutate('rate')`` bumps ``version``) and ``prototype/shared/crm-automation.js`` (the laser-co2 chain D+1, D+3,
D+7 and the D+30 review). Single tenant (``st_0009_single_tenant``): no row level security; every table keeps
``clinic_id`` (the installation id) and the same ``version`` optimistic lock as the rest of ``clinic.*``.

* ``clinic.service``: one row per service (``code`` is the stable key: ``clinic.treatment_plan.service_code`` and
  the finance entries use it). ``terms_version`` points at the CURRENT row of ``clinic.service_version``.
* ``clinic.service_version``: append-only snapshots of the terms that must not change under existing records:
  price, commission rate (basis points of the base, 10000 = 100 %), basis (``net``, ``list``, ``collected``),
  duration and room buffer. A change of any of them inserts the next version; a booking or a finance entry
  keeps the version it was made under ("Lịch đã đặt giữ giá và thời lượng tại lúc đặt"; PB02 rate snapshots).
  A trigger refuses UPDATE and DELETE of a version.
* ``clinic.protocol``: the follow-up chain of a treatment protocol as data: ``milestones`` is a JSON list of
  ``{"rule_key": "d1"|"d3"|"d7", "day": N}``, ``followup_days`` the day of the review recommendation (D+30 for
  laser-co2) and ``window_days`` how long after the session the chain still applies (45). The CRM rule engine
  (package B2) reads them; with no row it falls back to the constants it had, so nothing changes until staff edit
  a protocol. Upgrade seeds ``laser-co2`` from the delays the clinic has in ``clinic.crm_rule`` (d1, d3, d7) so a
  tuned clinic keeps its numbers.
* ``clinic.room``: treatment rooms (name, capacity, active). Doctors are NOT stored here: a doctor is a
  ``clinic.user_account`` of role ``doctor`` and the shift lives in ``clinic.staff_profiles`` (package M); the
  resources page reads both instead of keeping a second copy.
* ``clinic.room_block``: a time window a room cannot be booked ("Bảo trì thiết bị laser").

Only ``be_app`` gets privileges (the worker reads none of this).

Revision ID: u4_0010_services_resources
Revises: u7_0001_guide_tags
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u4_0010_services_resources"
down_revision = "u7_0001_guide_tags"
branch_labels = None
depends_on = None

TOUCHED = ("service", "protocol", "room")
BASES = "'net', 'list', 'collected'"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _seed_delay(rule_key: str, fallback: int) -> str:
    return (
        "COALESCE((SELECT r.delay_days FROM clinic.crm_rule r "
        f"WHERE r.clinic_id = c.id AND r.rule_key = '{rule_key}'), {fallback})"
    )


def upgrade() -> None:
    _sql("""
        CREATE TABLE clinic.service (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            code text NOT NULL CHECK (code ~ '^[a-z0-9][a-z0-9-]{1,39}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
            active boolean NOT NULL DEFAULT true,
            protocol_code text,
            room_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
            terms_version integer NOT NULL DEFAULT 1 CHECK (terms_version >= 1),
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, code),
            UNIQUE (clinic_id, id)
        )""")

    _sql(f"""
        CREATE TABLE clinic.service_version (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            service_id uuid NOT NULL,
            version_no integer NOT NULL CHECK (version_no >= 1),
            price_vnd bigint NOT NULL CHECK (price_vnd >= 0),
            rate_bp integer NOT NULL CHECK (rate_bp BETWEEN 0 AND 10000),
            basis text NOT NULL CHECK (basis IN ({BASES})),
            duration_min integer NOT NULL CHECK (duration_min BETWEEN 5 AND 480),
            buffer_min integer NOT NULL DEFAULT 0 CHECK (buffer_min BETWEEN 0 AND 120),
            changed_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (service_id, version_no),
            FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service (clinic_id, id),
            FOREIGN KEY (clinic_id, changed_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("""
        CREATE FUNCTION clinic.service_version_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
            RAISE EXCEPTION 'clinic.service_version is append-only';
        END
        $fn$""")
    _sql(
        "CREATE TRIGGER service_version_append_only BEFORE UPDATE OR DELETE ON clinic.service_version "
        "FOR EACH ROW EXECUTE FUNCTION clinic.service_version_append_only()"
    )

    _sql("""
        CREATE TABLE clinic.protocol (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            code text NOT NULL CHECK (code ~ '^[a-z0-9][a-z0-9-]{1,39}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
            milestones jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(milestones) = 'array'),
            followup_days integer CHECK (followup_days IS NULL OR followup_days BETWEEN 1 AND 365),
            window_days integer NOT NULL DEFAULT 45 CHECK (window_days BETWEEN 1 AND 365),
            active boolean NOT NULL DEFAULT true,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, code)
        )""")

    _sql("""
        CREATE TABLE clinic.room (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
            capacity integer NOT NULL DEFAULT 1 CHECK (capacity BETWEEN 1 AND 20),
            active boolean NOT NULL DEFAULT true,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, name),
            UNIQUE (clinic_id, id)
        )""")

    _sql("""
        CREATE TABLE clinic.room_block (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            room_id uuid NOT NULL,
            day date NOT NULL,
            starts_at time NOT NULL,
            ends_at time NOT NULL,
            reason text NOT NULL CHECK (length(reason) BETWEEN 1 AND 200),
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (starts_at < ends_at),
            FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX room_block_day_idx ON clinic.room_block (clinic_id, day, room_id)")

    for table in TOUCHED:
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")
    _sql("GRANT SELECT, INSERT ON clinic.service_version TO be_app")
    _sql("GRANT SELECT, INSERT, DELETE ON clinic.room_block TO be_app")

    # laser-co2: the chain the CRM engine had hard-coded, with the delays this clinic already tuned.
    _sql(f"""
        INSERT INTO clinic.protocol (clinic_id, code, name, milestones, followup_days, window_days)
        SELECT c.id, 'laser-co2', 'Laser CO2',
               jsonb_build_array(
                   jsonb_build_object('rule_key', 'd1', 'day', {_seed_delay("d1", 1)}),
                   jsonb_build_object('rule_key', 'd3', 'day', {_seed_delay("d3", 3)}),
                   jsonb_build_object('rule_key', 'd7', 'day', {_seed_delay("d7", 7)})),
               30, 45
          FROM clinic.clinic c
        ON CONFLICT (clinic_id, code) DO NOTHING""")


def downgrade() -> None:
    for table in ("room_block", "room", "protocol", "service_version", "service"):
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    _sql("DROP FUNCTION IF EXISTS clinic.service_version_append_only()")

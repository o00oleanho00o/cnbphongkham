"""zalo_uid <-> patient identity link: one-time codes, attempt log, SECURITY DEFINER functions (package P).

Adds to ``0003_clinic_agent_access`` (never edits it) what the ``patient_channel`` identity flow needs
(PLAN-AI01 section 5, ``pema.policy.identity``):

* ``clinic.identity_link_code``: a one-time code issued by reception for ONE patient. Only the SHA-256
  of the code is stored; it expires and is spent on first use. ``be_app`` issues it (DML, RLS).
* ``clinic.identity_link_attempt``: append-only log of link attempts per (channel, user); five FAILED
  attempts in an hour stop the chat from trying more (nobody can guess a code or enumerate phones).
* ``clinic_agent.link_identity_by_phone_hash``: the agent worker sends the SHA-256 of a phone number the
  patient typed. The function compares it with the same hash of ``clinic.patient.phone`` and, if exactly
  one patient matches, marks the link ``pending`` (a staff member confirms it). The worker never reads a
  phone number and never verifies on its own.
* ``clinic_agent.redeem_identity_code``: redeems a reception code; the link becomes ``verified`` with the
  issuing staff member as verifier. Only a hash travels.

Hash convention shared with ``pema.policy.identity.phone_hash``: lower-case hex SHA-256 of the national
phone format ``0xxxxxxxxx`` (``+84`` / ``84`` / ``0084`` prefixes folded to ``0``), computed in SQL by
``clinic_agent.norm_phone``. Every function refuses to run without a clinic context and audits (actor
``agent``). ``agent_worker`` gets EXECUTE on the two public functions only, nothing on the tables.

Revision ID: p0001_identity_link
Revises: 0003_clinic_agent_access
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p0001_identity_link"
down_revision = "0003_clinic_agent_access"
branch_labels = None
depends_on = None

PUBLIC_FUNCTIONS = (
    "clinic_agent.link_identity_by_phone_hash(text, text, text)",
    "clinic_agent.redeem_identity_code(text, text, text)",
)
HELPER_FUNCTIONS = (
    "clinic_agent.norm_phone(text)",
    "clinic_agent.link_attempts_exceeded(uuid, text, text)",
)


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("""
        CREATE TABLE clinic.identity_link_code (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            code_hash text NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
            issued_by uuid NOT NULL,
            expires_at timestamptz NOT NULL,
            used_at timestamptz,
            used_identity_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, code_hash),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, issued_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, used_identity_id) REFERENCES clinic.channel_identity (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX identity_link_code_patient_idx ON clinic.identity_link_code "
        "(clinic_id, patient_id, created_at DESC)"
    )
    _sql("""
        CREATE TABLE clinic.identity_link_attempt (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            channel text NOT NULL,
            external_user_id text NOT NULL,
            method text NOT NULL CHECK (method IN ('phone', 'code')),
            succeeded boolean NOT NULL,
            attempted_at timestamptz NOT NULL DEFAULT now()
        )""")
    _sql(
        "CREATE INDEX identity_link_attempt_idx ON clinic.identity_link_attempt "
        "(clinic_id, channel, external_user_id, attempted_at DESC)"
    )
    for table in ("identity_link_code", "identity_link_attempt"):
        _sql(f"ALTER TABLE clinic.{table} ENABLE ROW LEVEL SECURITY")
        _sql(
            f"CREATE POLICY clinic_isolation ON clinic.{table} "
            "USING (clinic_id = ctx.current_clinic_id()) "
            "WITH CHECK (clinic_id = ctx.current_clinic_id())"
        )
    # the attempt log is evidence: staff may read it, nobody rewrites it
    _sql("REVOKE UPDATE, DELETE ON clinic.identity_link_attempt FROM be_app")
    _sql("REVOKE ALL ON clinic.identity_link_code, clinic.identity_link_attempt FROM agent_worker")

    _sql("""
        CREATE FUNCTION clinic_agent.norm_phone(p text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
            SELECT CASE
                WHEN d LIKE '0084%' THEN '0' || substr(d, 5)
                WHEN d LIKE '84%' AND length(d) IN (11, 12) THEN
                    CASE WHEN substr(d, 3, 1) = '0' THEN substr(d, 3) ELSE '0' || substr(d, 3) END
                ELSE d
            END
            FROM (SELECT regexp_replace(coalesce(p, ''), '[^0-9]', '', 'g') AS d) s
        $$""")
    _sql("""
        CREATE FUNCTION clinic_agent.link_attempts_exceeded(p_clinic uuid, p_channel text, p_uid text)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, clinic AS $$
            SELECT count(*) >= 5
              FROM clinic.identity_link_attempt a
             WHERE a.clinic_id = p_clinic AND a.channel = p_channel AND a.external_user_id = p_uid
               AND NOT a.succeeded AND a.attempted_at > now() - interval '1 hour'
        $$""")

    _sql("""
        CREATE FUNCTION clinic_agent.link_identity_by_phone_hash(
            p_channel text, p_external_user_id text, p_phone_hash text)
        RETURNS TABLE (outcome text, patient_id uuid, patient_code text, identity_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, clinic_agent, ctx AS $$
        #variable_conflict use_column
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_identity clinic.channel_identity%ROWTYPE;
            v_ids uuid[];
            v_codes text[];
            v_n integer;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_phone_hash IS NULL OR p_phone_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid phone hash';
            END IF;
            IF clinic_agent.link_attempts_exceeded(v_clinic, p_channel, p_external_user_id) THEN
                RETURN QUERY SELECT 'rate_limited'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE SET last_inbound_at = now()
            RETURNING * INTO v_identity;

            IF v_identity.verification_status = 'verified' THEN
                RETURN QUERY SELECT 'already_verified'::text, v_identity.patient_id,
                    (SELECT pt.code FROM clinic.patient pt
                      WHERE pt.clinic_id = v_clinic AND pt.id = v_identity.patient_id),
                    v_identity.id;
                RETURN;
            END IF;
            IF v_identity.verification_status = 'rejected' THEN
                RETURN QUERY SELECT 'rejected_by_staff'::text, NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            SELECT array_agg(pt.id), array_agg(pt.code) INTO v_ids, v_codes
              FROM clinic.patient pt
             WHERE pt.clinic_id = v_clinic AND pt.phone IS NOT NULL
               AND encode(sha256(convert_to(clinic_agent.norm_phone(pt.phone), 'UTF8')), 'hex') = p_phone_hash;
            v_n := coalesce(array_length(v_ids, 1), 0);

            IF v_n <> 1 THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'phone', false);
                RETURN QUERY SELECT (CASE WHEN v_n = 0 THEN 'no_match' ELSE 'ambiguous' END)::text,
                    NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            UPDATE clinic.channel_identity i
               SET patient_id = v_ids[1], verification_status = 'pending'
             WHERE i.clinic_id = v_clinic AND i.id = v_identity.id;
            INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
            VALUES (v_clinic, p_channel, p_external_user_id, 'phone', true);
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'identity.link_candidate', 'channel_identity', v_identity.id::text,
                    jsonb_build_object('method', 'phone', 'channel', p_channel));
            RETURN QUERY SELECT 'candidate_created'::text, v_ids[1], v_codes[1], v_identity.id;
        END $$""")

    _sql("""
        CREATE FUNCTION clinic_agent.redeem_identity_code(
            p_channel text, p_external_user_id text, p_code_hash text)
        RETURNS TABLE (outcome text, patient_id uuid, patient_code text, identity_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, clinic, clinic_agent, ctx AS $$
        #variable_conflict use_column
        DECLARE
            v_clinic uuid := ctx.current_clinic_id();
            v_identity clinic.channel_identity%ROWTYPE;
            v_code clinic.identity_link_code%ROWTYPE;
            v_patient_code text;
        BEGIN
            IF v_clinic IS NULL THEN RAISE EXCEPTION 'no clinic context'; END IF;
            IF p_code_hash IS NULL OR p_code_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'invalid code hash';
            END IF;
            IF clinic_agent.link_attempts_exceeded(v_clinic, p_channel, p_external_user_id) THEN
                RETURN QUERY SELECT 'rate_limited'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            SELECT * INTO v_code FROM clinic.identity_link_code c
             WHERE c.clinic_id = v_clinic AND c.code_hash = p_code_hash FOR UPDATE;
            IF NOT FOUND OR v_code.used_at IS NOT NULL THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'invalid_code'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;
            IF v_code.expires_at < now() THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'expired_code'::text, NULL::uuid, NULL::text, NULL::uuid;
                RETURN;
            END IF;

            INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, last_inbound_at)
            VALUES (v_clinic, p_channel, p_external_user_id, now())
            ON CONFLICT (clinic_id, channel, external_user_id) DO UPDATE SET last_inbound_at = now()
            RETURNING * INTO v_identity;

            IF v_identity.verification_status = 'verified' AND v_identity.patient_id <> v_code.patient_id THEN
                INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
                VALUES (v_clinic, p_channel, p_external_user_id, 'code', false);
                RETURN QUERY SELECT 'conflict'::text, NULL::uuid, NULL::text, v_identity.id;
                RETURN;
            END IF;

            UPDATE clinic.channel_identity i
               SET patient_id = v_code.patient_id, verification_status = 'verified',
                   verified_at = now(), verified_by = v_code.issued_by
             WHERE i.clinic_id = v_clinic AND i.id = v_identity.id;
            UPDATE clinic.identity_link_code c
               SET used_at = now(), used_identity_id = v_identity.id
             WHERE c.clinic_id = v_clinic AND c.id = v_code.id;
            INSERT INTO clinic.identity_link_attempt (clinic_id, channel, external_user_id, method, succeeded)
            VALUES (v_clinic, p_channel, p_external_user_id, 'code', true);
            INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type, entity_id, details)
            VALUES (v_clinic, 'agent', 'identity.verified_by_code', 'channel_identity', v_identity.id::text,
                    jsonb_build_object('channel', p_channel, 'issued_by', v_code.issued_by));
            SELECT pt.code INTO v_patient_code FROM clinic.patient pt
             WHERE pt.clinic_id = v_clinic AND pt.id = v_code.patient_id;
            RETURN QUERY SELECT 'verified'::text, v_code.patient_id, v_patient_code, v_identity.id;
        END $$""")

    for fn in (*PUBLIC_FUNCTIONS, *HELPER_FUNCTIONS):
        _sql(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
    for fn in PUBLIC_FUNCTIONS:
        _sql(f"GRANT EXECUTE ON FUNCTION {fn} TO agent_worker")


def downgrade() -> None:
    for fn in (*PUBLIC_FUNCTIONS, *HELPER_FUNCTIONS):
        _sql(f"DROP FUNCTION IF EXISTS {fn}")
    _sql("DROP TABLE IF EXISTS clinic.identity_link_attempt")
    _sql("DROP TABLE IF EXISTS clinic.identity_link_code")

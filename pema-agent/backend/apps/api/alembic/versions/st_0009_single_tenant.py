"""Single tenant (package ST-A): one clinic per installation, no row level security, no clinic context.

Until this revision one database could host several clinics: every row carried ``clinic_id``, a policy
``clinic_isolation`` compared it with ``ctx.current_clinic_id()`` (the transaction-local setting
``app.clinic_id``) and two lookups (``ctx.resolve_clinic``, ``ctx.list_active_clinic_ids``) served the moments
before a clinic was known. Each installation is now ONE clinic with its own database, so all of that goes.

What stays: the ``clinic_id`` column of every table (it is the fixed "installation id": the foreign keys, the
composite keys and ~4500 tests keep working), the roles and their grants, the ``clinic_agent`` views and
functions, the audit trail, consent, PII masking.

What this revision does:

* ``clinic.clinic`` may hold EXACTLY ONE row, enforced by the database: column ``singleton boolean NOT NULL
  DEFAULT true`` with ``CHECK (singleton)`` and ``UNIQUE (singleton)``, so a second INSERT fails. A trigger also
  refuses to DELETE the row (its id is the installation id and every other table points at it). The upgrade
  stops with a clear message when the database already holds more than one clinic (merge or split it first).
* ``clinic.ensure_clinic(name, slug, timezone, id)``: idempotent create of that one row (never renames, never
  changes the id; with an ``id`` that differs from the installed one it raises). Not executable by the runtime
  roles: it is for this migration, the seed and the tests, run by the owner. This revision calls it with
  ``PEMA_CLINIC_NAME`` (default ``Pema Clinic``), the fixed slug ``clinic`` and, when set, ``PEMA_CLINIC_ID``
  as the id (otherwise one id is generated, once). A database that already has its clinic keeps it.
* ``ctx.the_clinic_id()``: STABLE, SECURITY DEFINER, returns the id of the only clinic and RAISES when there is
  none (fail closed: a half-installed database must not answer "no rows" as if it were empty). Executable by
  both runtime roles; it lives in ``ctx`` because ``agent_worker`` has no privilege on schema ``clinic``.
* every view and every SECURITY DEFINER function that compared with, or read, ``ctx.current_clinic_id()`` is
  re-created with ``ctx.the_clinic_id()``: ``clinic_agent.*`` (the nine views of 0003, ``review_item_summary``,
  ``touch_identity``, ``resolve_identity``, ``create_review_item``, ``record_inbound_message``,
  ``record_outbound_message``, the identity-link functions of p0001, the retention functions of h2_0007). The
  text is rewritten from the catalog (``pg_get_functiondef`` / ``pg_get_viewdef``), so attributes,
  ``security_barrier``, grants, owner and the fixed ``search_path`` ending in ``pg_temp`` (g_0006) are kept.
  The upgrade then refuses to finish if any function, view, policy or default still names the old function.
* every policy ``clinic_isolation`` on ``clinic.*`` and ``agent.*`` is dropped and ``ROW LEVEL SECURITY`` is
  disabled (NO FORCE first where it was forced) on every table of both schemas.
* ``ctx.current_clinic_id``, ``ctx.resolve_clinic`` and ``ctx.list_active_clinic_ids`` are dropped (a plain DROP,
  without CASCADE: any leftover dependent stops the migration).

Security consequence, accepted on purpose: without RLS ``be_app`` and ``agent_worker`` read every row of the
tables they hold a grant on, whatever ``app.clinic_id`` says. That is fine because there is one clinic in the
database. Nothing else is loosened: ``agent_worker`` still has no privilege on ``clinic.*`` and reaches the
clinic only through the ``clinic_agent`` views and functions (the views still filter by the installation id,
defence in depth); ``be_app`` keeps exactly the grants it had (``audit_log`` insert/select only, the identity
attempt log without UPDATE/DELETE); ``clinic.audit_log`` is still append-only (trigger); no new EXECUTE grant
goes to PUBLIC; every SECURITY DEFINER function still pins ``search_path`` with ``pg_temp`` last.

The downgrade restores the policies, RLS, the three ``ctx`` functions and the old function bodies, and drops
the singleton constraint, the guard trigger, ``ensure_clinic`` and ``the_clinic_id``. The clinic row stays.

Revision ID: st_0009_single_tenant
Revises: h_0008_merge_heads
"""

from __future__ import annotations

import os
import re
import uuid

import sqlalchemy as sa
from alembic import op

revision = "st_0009_single_tenant"
down_revision = "h_0008_merge_heads"
branch_labels = None
depends_on = None

DEFAULT_CLINIC_NAME = "Pema Clinic"
INSTALLATION_SLUG = "clinic"
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
SCHEMAS = ("clinic", "agent")
OLD_FN = "ctx.current_clinic_id()"
NEW_FN = "ctx.the_clinic_id()"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _install_name() -> str:
    name = os.environ.get("PEMA_CLINIC_NAME", "").strip()
    return name or DEFAULT_CLINIC_NAME


def _install_id() -> str | None:
    raw = os.environ.get("PEMA_CLINIC_ID", "").strip()
    if not raw:
        return None
    return str(uuid.UUID(raw))


def _rewrite_objects(old: str, new: str) -> None:
    """Re-create every view and function of the Pema schemas whose text names ``old``, with ``new`` instead."""
    old_pattern = re.escape(old)
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                f record;
                v record;
                src text;
            BEGIN
                FOR f IN
                    SELECT p.oid
                      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname IN ('ctx', 'clinic', 'clinic_agent', 'agent')
                       AND p.prokind = 'f' AND p.prosrc ~ '{old_pattern}'
                LOOP
                    src := regexp_replace(pg_get_functiondef(f.oid), '{old_pattern}', '{new}', 'g');
                    EXECUTE src;
                END LOOP;
                FOR v IN
                    SELECT c.oid, c.oid::regclass::text AS name, c.reloptions
                      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname IN ('ctx', 'clinic', 'clinic_agent', 'agent') AND c.relkind = 'v'
                       AND pg_get_viewdef(c.oid) ~ '{old_pattern}'
                LOOP
                    src := regexp_replace(pg_get_viewdef(v.oid), '{old_pattern}', '{new}', 'g');
                    src := regexp_replace(src, ';\\s*$', '');
                    EXECUTE format(
                        'CREATE OR REPLACE VIEW %s %s AS %s', v.name,
                        CASE WHEN v.reloptions IS NULL THEN ''
                             ELSE 'WITH (' || array_to_string(v.reloptions, ', ') || ')' END,
                        src);
                END LOOP;
            END $$
            """
        )
    )


def _assert_no_reference(name: str) -> None:
    """Stop when a function, view, policy or column default of the Pema schemas still names ``name``."""
    pattern = re.escape(name)
    op.execute(
        sa.text(
            f"""
            DO $$
            DECLARE
                left_over text;
            BEGIN
                SELECT string_agg(what, ', ') INTO left_over FROM (
                    SELECT p.oid::regprocedure::text AS what
                      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname IN ('ctx', 'clinic', 'clinic_agent', 'agent')
                       AND p.prokind = 'f' AND p.prosrc ~ '{pattern}'
                    UNION ALL
                    SELECT c.oid::regclass::text
                      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname IN ('ctx', 'clinic', 'clinic_agent', 'agent') AND c.relkind = 'v'
                       AND pg_get_viewdef(c.oid) ~ '{pattern}'
                    UNION ALL
                    SELECT 'policy ' || polname FROM pg_policy
                     WHERE coalesce(pg_get_expr(polqual, polrelid), '') ~ '{pattern}'
                        OR coalesce(pg_get_expr(polwithcheck, polrelid), '') ~ '{pattern}'
                    UNION ALL
                    SELECT 'default ' || d.adrelid::regclass::text FROM pg_attrdef d
                     WHERE pg_get_expr(d.adbin, d.adrelid) ~ '{pattern}'
                ) refs;
                IF left_over IS NOT NULL THEN
                    RAISE EXCEPTION 'still referencing {name}: %', left_over;
                END IF;
            END $$
            """
        )
    )


def upgrade() -> None:
    # ---------------------------------------------------------------- exactly one clinic
    _sql("""
        DO $$ BEGIN
            IF (SELECT count(*) FROM clinic.clinic) > 1 THEN
                RAISE EXCEPTION 'clinic.clinic holds more than one clinic: one installation is one clinic';
            END IF;
        END $$""")
    _sql("ALTER TABLE clinic.clinic ADD COLUMN singleton boolean NOT NULL DEFAULT true")
    _sql("ALTER TABLE clinic.clinic ADD CONSTRAINT clinic_singleton_is_true CHECK (singleton)")
    _sql("ALTER TABLE clinic.clinic ADD CONSTRAINT clinic_singleton_key UNIQUE (singleton)")
    _sql(
        "CREATE FUNCTION clinic.clinic_undeletable() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'the clinic row is the installation id and cannot be deleted'; END $$"
    )
    _sql(
        "CREATE TRIGGER clinic_no_delete BEFORE DELETE ON clinic.clinic "
        "FOR EACH ROW EXECUTE FUNCTION clinic.clinic_undeletable()"
    )
    _sql(f"""
        CREATE FUNCTION clinic.ensure_clinic(
            p_name text,
            p_slug text DEFAULT '{INSTALLATION_SLUG}',
            p_timezone text DEFAULT '{DEFAULT_TIMEZONE}',
            p_id uuid DEFAULT NULL)
        RETURNS uuid LANGUAGE plpgsql SET search_path = pg_catalog, clinic, pg_temp AS $$
        DECLARE
            v_id uuid;
        BEGIN
            INSERT INTO clinic.clinic (id, slug, name, timezone)
            VALUES (COALESCE(p_id, gen_random_uuid()), p_slug, p_name, p_timezone)
            ON CONFLICT (singleton) DO NOTHING;
            SELECT id INTO STRICT v_id FROM clinic.clinic;
            IF p_id IS NOT NULL AND v_id <> p_id THEN
                RAISE EXCEPTION 'the installed clinic has another id than the one asked for';
            END IF;
            RETURN v_id;
        END $$""")
    _sql("REVOKE ALL ON FUNCTION clinic.ensure_clinic(text, text, text, uuid) FROM PUBLIC")
    _sql("REVOKE ALL ON FUNCTION clinic.ensure_clinic(text, text, text, uuid) FROM be_app, agent_worker")

    _sql("""
        CREATE FUNCTION ctx.the_clinic_id() RETURNS uuid
        LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, clinic, pg_temp AS $$
        DECLARE
            v_id uuid;
        BEGIN
            SELECT id INTO v_id FROM clinic.clinic;
            IF v_id IS NULL THEN
                RAISE EXCEPTION 'no clinic installed: run clinic.ensure_clinic first';
            END IF;
            RETURN v_id;
        END $$""")
    _sql("REVOKE ALL ON FUNCTION ctx.the_clinic_id() FROM PUBLIC")
    _sql("GRANT EXECUTE ON FUNCTION ctx.the_clinic_id() TO be_app, agent_worker")

    op.execute(
        sa.text("SELECT clinic.ensure_clinic(:name, :slug, :tz, CAST(:id AS uuid))").bindparams(
            name=_install_name(), slug=INSTALLATION_SLUG, tz=DEFAULT_TIMEZONE, id=_install_id()
        )
    )

    # ---------------------------------------------------------------- no clinic context any more
    _rewrite_objects(OLD_FN, NEW_FN)

    _sql("""
        DO $$
        DECLARE
            r record;
        BEGIN
            FOR r IN SELECT schemaname, tablename, policyname FROM pg_policies
                      WHERE schemaname IN ('clinic', 'agent')
            LOOP
                EXECUTE format('DROP POLICY %I ON %I.%I', r.policyname, r.schemaname, r.tablename);
            END LOOP;
            FOR r IN SELECT n.nspname AS schemaname, c.relname AS tablename, c.relforcerowsecurity AS forced
                       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                      WHERE n.nspname IN ('clinic', 'agent') AND c.relkind IN ('r', 'p') AND c.relrowsecurity
            LOOP
                IF r.forced THEN
                    EXECUTE format('ALTER TABLE %I.%I NO FORCE ROW LEVEL SECURITY', r.schemaname, r.tablename);
                END IF;
                EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY', r.schemaname, r.tablename);
            END LOOP;
        END $$""")

    _sql("DROP FUNCTION ctx.resolve_clinic(text)")
    _sql("DROP FUNCTION ctx.list_active_clinic_ids()")
    _sql("DROP FUNCTION ctx.current_clinic_id()")
    _assert_no_reference("current_clinic_id")
    _assert_no_reference("app.clinic_id")


def downgrade() -> None:
    _sql(
        "CREATE FUNCTION ctx.current_clinic_id() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.clinic_id', true), '')::uuid $$"
    )
    _sql("REVOKE ALL ON FUNCTION ctx.current_clinic_id() FROM PUBLIC")
    _sql("GRANT EXECUTE ON FUNCTION ctx.current_clinic_id() TO be_app, agent_worker")
    _sql(
        "CREATE FUNCTION ctx.resolve_clinic(p_slug text) RETURNS uuid LANGUAGE sql STABLE "
        "SECURITY DEFINER SET search_path = pg_catalog, clinic, pg_temp AS "
        "$$ SELECT id FROM clinic.clinic WHERE slug = p_slug AND active $$"
    )
    _sql(
        "CREATE FUNCTION ctx.list_active_clinic_ids() RETURNS SETOF uuid LANGUAGE sql STABLE "
        "SECURITY DEFINER SET search_path = pg_catalog, clinic, pg_temp AS "
        "$$ SELECT id FROM clinic.clinic WHERE active ORDER BY created_at $$"
    )
    for fn in ("ctx.resolve_clinic(text)", "ctx.list_active_clinic_ids()"):
        _sql(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        _sql(f"GRANT EXECUTE ON FUNCTION {fn} TO be_app, agent_worker")

    _rewrite_objects(NEW_FN, OLD_FN)

    _sql("""
        DO $$
        DECLARE
            r record;
        BEGIN
            FOR r IN SELECT n.nspname AS schemaname, c.relname AS tablename
                       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                      WHERE n.nspname IN ('clinic', 'agent') AND c.relkind IN ('r', 'p')
            LOOP
                EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.schemaname, r.tablename);
                IF r.schemaname = 'clinic' AND r.tablename = 'clinic' THEN
                    EXECUTE 'CREATE POLICY clinic_isolation ON clinic.clinic '
                            'USING (id = ctx.current_clinic_id()) WITH CHECK (id = ctx.current_clinic_id())';
                ELSE
                    EXECUTE format(
                        'CREATE POLICY clinic_isolation ON %I.%I USING (clinic_id = ctx.current_clinic_id()) '
                        'WITH CHECK (clinic_id = ctx.current_clinic_id())', r.schemaname, r.tablename);
                END IF;
            END LOOP;
        END $$""")

    _sql("DROP FUNCTION ctx.the_clinic_id()")
    _sql("DROP FUNCTION clinic.ensure_clinic(text, text, text, uuid)")
    _sql("DROP TRIGGER clinic_no_delete ON clinic.clinic")
    _sql("DROP FUNCTION clinic.clinic_undeletable()")
    _sql("ALTER TABLE clinic.clinic DROP CONSTRAINT clinic_singleton_key")
    _sql("ALTER TABLE clinic.clinic DROP CONSTRAINT clinic_singleton_is_true")
    _sql("ALTER TABLE clinic.clinic DROP COLUMN singleton")
    _assert_no_reference("the_clinic_id")

"""SECURITY DEFINER functions: ``pg_temp`` last in their ``search_path``; no TEMP right for PUBLIC (package G).

Every SECURITY DEFINER function of ``ctx`` and ``clinic_agent`` already pins ``SET search_path = pg_catalog,
...``. What was missing is naming ``pg_temp`` explicitly and LAST: a schema that is not in the path is searched
first when it is the temporary schema, so a role allowed to create temporary objects could shadow a relation or
a type that a function names without a schema. Naming it last turns that off (the pattern of the PostgreSQL
documentation, "Writing SECURITY DEFINER Functions Safely"). Done for EVERY definer function found in the two
schemas, so a function added by a later package without it is fixed by running this revision again and a
function with no ``search_path`` at all stops the migration.

``REVOKE TEMPORARY ... FROM PUBLIC``: the runtime roles have no use for temporary tables (the application never
creates one), so the right goes away and the shadowing above has nothing to start from.

Revision ID: g_0006_definer_search_path
Revises: g_0005_merge_heads
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g_0006_definer_search_path"
down_revision = "g_0005_merge_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                f record;
            BEGIN
                FOR f IN
                    SELECT p.oid::regprocedure AS sig,
                           (SELECT substr(c, length('search_path=') + 1)
                              FROM unnest(p.proconfig) AS c WHERE c LIKE 'search_path=%') AS sp
                      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE p.prosecdef AND n.nspname IN ('ctx', 'clinic_agent')
                LOOP
                    IF f.sp IS NULL THEN
                        RAISE EXCEPTION 'SECURITY DEFINER function % has no fixed search_path', f.sig;
                    END IF;
                    IF f.sp NOT LIKE '%pg_temp%' THEN
                        EXECUTE format('ALTER FUNCTION %s SET search_path = %s, pg_temp', f.sig, f.sp);
                    END IF;
                END LOOP;
                BEGIN
                    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
                EXCEPTION WHEN insufficient_privilege THEN
                    RAISE NOTICE 'not the database owner: REVOKE TEMPORARY ... FROM PUBLIC skipped';
                END;
            END $$
            """
        )
    )


def downgrade() -> None:
    """Nothing to undo: ``pg_temp`` last only closes a door, and the TEMP right is not given back."""

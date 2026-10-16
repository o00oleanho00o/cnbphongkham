#!/usr/bin/env bash
# Create or refresh the runtime role of the clinic API and its password, idempotently.
#
#   be_app        API process: DML on clinic.* (no row level security: the database holds ONE clinic, so
#                 the grants of the baseline are the whole access control).
#
# The agent service has no role here and reads nothing of this database (.claude/rules/agent-crm-boundary.md).
#
# One database = one clinic. Roles are cluster-wide in Postgres: do not point two clinics' stacks at the same
# Postgres cluster (each clinic has its own Postgres, see infra/README.md "One system, one clinic").
#
# What this script does NOT do: create schemas, tables, grants or the clinic row. Those belong to the Alembic
# revisions (``0001_baseline``: ctx, clinic and the single clinic), which `migrate.sh` runs right after this
# script. The role is created here (and again, harmlessly, by the baseline) so that the password comes from
# the environment and never from a file in git.
#
# Inputs (environment, never arguments, so no password shows in `ps`):
#   PEMA_MIGRATION_DATABASE_URL   owner/superuser URL, e.g. postgresql+psycopg://postgres:...@host:5432/pema
#   PEMA_BE_APP_PASSWORD          password of be_app          (empty/unset: the role stays NOLOGIN)
#
# Always: REVOKE CONNECT on the database from PUBLIC and grant it to be_app only, so no other role (the agent's
# agent_rt_app above all) can connect (.claude/rules/agent-crm-boundary.md, L1).
#
# Safe to rerun: also the way to ROTATE a password (change the variable, run it, restart the services).
set -euo pipefail

: "${PEMA_MIGRATION_DATABASE_URL:?set PEMA_MIGRATION_DATABASE_URL (owner/superuser URL)}"

# Turn the SQLAlchemy URL into PG* environment variables for psql (keeps the password out of the argv).
PY="$(command -v python3 || command -v python)"
eval "$("$PY" - <<'PYEOF'
import os, shlex, sys
from urllib.parse import urlsplit, unquote

url = urlsplit(os.environ["PEMA_MIGRATION_DATABASE_URL"].replace("+psycopg", "", 1))
if url.scheme not in ("postgresql", "postgres"):
    sys.exit("PEMA_MIGRATION_DATABASE_URL must be a postgresql URL")
pairs = {
    "PGHOST": url.hostname or "localhost",
    "PGPORT": str(url.port or 5432),
    "PGUSER": unquote(url.username or "postgres"),
    "PGPASSWORD": unquote(url.password or ""),
    "PGDATABASE": (url.path or "/pema").lstrip("/") or "pema",
}
for key, value in pairs.items():
    print(f"export {key}={shlex.quote(value)}")
PYEOF
)"

# Passwords are read by psql itself (`\getenv`, psql >= 15) so they never appear in the argument list.
export PEMA_BE_APP_PASSWORD="${PEMA_BE_APP_PASSWORD:-}"
psql --no-psqlrc --set=ON_ERROR_STOP=1 <<'SQL'
-- The ALTER ROLE ... PASSWORD statement must never reach the server log in clear text.
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_min_error_statement = 'panic';

\getenv be_app_pw PEMA_BE_APP_PASSWORD

SELECT current_database() AS dbname \gset

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'be_app') THEN
    CREATE ROLE be_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;

SELECT format('ALTER ROLE be_app LOGIN PASSWORD %L', :'be_app_pw')
 WHERE length(:'be_app_pw') > 0 \gexec

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'dbname') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO be_app', :'dbname') \gexec

SELECT rolname,
       CASE WHEN rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END AS login,
       rolsuper, rolbypassrls
  FROM pg_roles WHERE rolname = 'be_app';
SQL

echo "bootstrap-roles: done (database ${PGDATABASE})"

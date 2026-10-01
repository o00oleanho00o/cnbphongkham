#!/usr/bin/env bash
# Create or refresh the two runtime roles and their passwords, idempotently.
#
#   be_app        API process: DML on clinic.* and agent.*, RLS applies.
#   agent_worker  worker process: DML on agent.*, reads clinic_agent views, NOTHING on clinic.*.
#
# What this script does NOT do: create schemas, tables, RLS or grants. Those belong to the Alembic revisions
# 0001..0003 (ctx, clinic, agent, clinic_agent), which `migrate.sh` runs right after this script. The roles
# are created here (and again, harmlessly, by revision 0001) so that the passwords come from the environment
# and never from a file in git.
#
# Inputs (environment, never arguments, so no password shows in `ps`):
#   PEMA_MIGRATION_DATABASE_URL   owner/superuser URL, e.g. postgresql+psycopg://postgres:...@host:5432/pema
#   PEMA_BE_APP_PASSWORD          password of be_app          (empty/unset: the role stays NOLOGIN)
#   PEMA_AGENT_WORKER_PASSWORD    password of agent_worker    (empty/unset: the role stays NOLOGIN)
#   PEMA_BOOTSTRAP_HARDEN_CONNECT true (default): REVOKE CONNECT on the database from PUBLIC and grant it to
#                                 the two roles only.
#
# Safe to rerun: also the way to ROTATE a password (change the variable, run it, restart the services).
set -euo pipefail

: "${PEMA_MIGRATION_DATABASE_URL:?set PEMA_MIGRATION_DATABASE_URL (owner/superuser URL)}"
HARDEN="${PEMA_BOOTSTRAP_HARDEN_CONNECT:-true}"

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
export PEMA_AGENT_WORKER_PASSWORD="${PEMA_AGENT_WORKER_PASSWORD:-}"
psql --no-psqlrc --set=ON_ERROR_STOP=1 --set=harden="$HARDEN" <<'SQL'
-- The ALTER ROLE ... PASSWORD statement must never reach the server log in clear text.
SET log_statement = 'none';
SET log_min_duration_statement = -1;
SET log_min_error_statement = 'panic';

\getenv be_app_pw PEMA_BE_APP_PASSWORD
\getenv agent_worker_pw PEMA_AGENT_WORKER_PASSWORD

SELECT current_database() AS dbname \gset

-- pgvector is created by revision 0002 as well; creating it here lets a NON-superuser owner run the
-- migrations when a superuser only bootstraps (managed/cloud Postgres).
CREATE EXTENSION IF NOT EXISTS vector;

DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['be_app', 'agent_worker'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', r);
    END IF;
  END LOOP;
END $$;

SELECT format('ALTER ROLE be_app LOGIN PASSWORD %L', :'be_app_pw')
 WHERE length(:'be_app_pw') > 0 \gexec
SELECT format('ALTER ROLE agent_worker LOGIN PASSWORD %L', :'agent_worker_pw')
 WHERE length(:'agent_worker_pw') > 0 \gexec

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'dbname')
 WHERE :'harden' = 'true' \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO be_app, agent_worker', :'dbname')
 WHERE :'harden' = 'true' \gexec

SELECT rolname,
       CASE WHEN rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END AS login,
       rolsuper, rolbypassrls
  FROM pg_roles WHERE rolname IN ('be_app', 'agent_worker') ORDER BY rolname;
SQL

echo "bootstrap-roles: done (database ${PGDATABASE})"

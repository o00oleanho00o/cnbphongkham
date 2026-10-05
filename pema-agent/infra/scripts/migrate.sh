#!/usr/bin/env bash
# Run the database migrations: wait for Postgres, bootstrap the roles, `alembic upgrade heads`, then check that
# the database holds exactly ONE clinic (one installation = one clinic) and print its name.
#
# The clinic row is created by the migration `st_0009_single_tenant` from PEMA_CLINIC_NAME (default "Pema Clinic")
# and, when set, PEMA_CLINIC_ID, on a database that has none. Rerunning never renames it or changes its id.
#
# `heads` (plural) applies every branch head, because parallel packages add revisions with
# down_revision = "0003_clinic_agent_access" and package G merges them later (CONTRACTS-AI01 section 5). When
# G has produced a single head this command is identical to `upgrade head`. The script reports how many heads
# it found; it never creates a merge revision itself (that is a reviewed change, not a deploy step).
#
# Environment: PEMA_MIGRATION_DATABASE_URL (owner/superuser URL), PEMA_BE_APP_PASSWORD,
# PEMA_AGENT_WORKER_PASSWORD; optional PEMA_CLINIC_NAME, PEMA_CLINIC_ID, PEMA_SKIP_ROLE_BOOTSTRAP=true,
# PEMA_MIGRATE_WAIT_SECONDS (default 60).
# Working directory: the folder that holds apps/api/alembic.ini (/app in the image, backend/ in the repo).
set -euo pipefail

: "${PEMA_MIGRATION_DATABASE_URL:?set PEMA_MIGRATION_DATABASE_URL (owner/superuser URL)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INI="${PEMA_ALEMBIC_INI:-apps/api/alembic.ini}"
WAIT="${PEMA_MIGRATE_WAIT_SECONDS:-60}"
PY="$(command -v python3 || command -v python)"

echo "migrate: waiting for Postgres (up to ${WAIT}s)"
"$PY" - "$WAIT" <<'PYEOF'
import os, sys, time
import psycopg

url = os.environ["PEMA_MIGRATION_DATABASE_URL"].replace("+psycopg", "", 1)
deadline = time.monotonic() + int(sys.argv[1])
while True:
    try:
        with psycopg.connect(url, connect_timeout=3):
            break
    except psycopg.OperationalError as exc:
        if time.monotonic() > deadline:
            sys.exit(f"migrate: Postgres not reachable: {type(exc).__name__}")
        time.sleep(2)
PYEOF

if [ "${PEMA_SKIP_ROLE_BOOTSTRAP:-false}" != "true" ]; then
  "$HERE/bootstrap-roles.sh"
fi

if command -v alembic >/dev/null 2>&1; then ALEMBIC=(alembic); else ALEMBIC=(uv run alembic); fi

HEADS="$("${ALEMBIC[@]}" -c "$INI" heads | grep -c '(head)' || true)"
echo "migrate: ${HEADS} head(s) in the revision tree"
if [ "$HEADS" -gt 1 ]; then
  echo "migrate: more than one head; applying all of them (package G merges the heads)"
fi

"${ALEMBIC[@]}" -c "$INI" upgrade heads
"${ALEMBIC[@]}" -c "$INI" current

# One installation = one clinic: the migration must have left exactly one row in clinic.clinic. Fail closed
# otherwise (an empty table means a half-installed database, two rows means a database that was shared).
"$PY" - <<'PYEOF'
import os, sys, uuid
import psycopg

url = os.environ["PEMA_MIGRATION_DATABASE_URL"].replace("+psycopg", "", 1)
with psycopg.connect(url, connect_timeout=5) as conn, conn.cursor() as cur:
    cur.execute("SELECT id, name FROM clinic.clinic ORDER BY created_at, id")
    rows = cur.fetchall()
if len(rows) != 1:
    sys.exit(f"migrate: clinic.clinic holds {len(rows)} row(s), expected exactly 1 (one system = one clinic)")
clinic_id, name = rows[0]
wanted_id = os.environ.get("PEMA_CLINIC_ID", "").strip()
if wanted_id and uuid.UUID(wanted_id) != clinic_id:
    sys.exit("migrate: PEMA_CLINIC_ID differs from the id of the installed clinic; refusing to continue")
print(f"migrate: clinic {name!r} (id {clinic_id}), exactly one row in clinic.clinic")
wanted_name = os.environ.get("PEMA_CLINIC_NAME", "").strip()
if wanted_name and wanted_name != name:
    print("migrate: note: PEMA_CLINIC_NAME differs from the installed name; the installed clinic is never renamed")
PYEOF
echo "migrate: done"

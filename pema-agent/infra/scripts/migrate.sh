#!/usr/bin/env bash
# Run the database migrations: wait for Postgres, bootstrap the roles, `alembic upgrade heads`.
#
# `heads` (plural) applies every branch head, because parallel packages add revisions with
# down_revision = "0003_clinic_agent_access" and package G merges them later (CONTRACTS-AI01 section 5). When
# G has produced a single head this command is identical to `upgrade head`. The script reports how many heads
# it found; it never creates a merge revision itself (that is a reviewed change, not a deploy step).
#
# Environment: PEMA_MIGRATION_DATABASE_URL (owner/superuser URL), PEMA_BE_APP_PASSWORD,
# PEMA_AGENT_WORKER_PASSWORD; optional PEMA_SKIP_ROLE_BOOTSTRAP=true, PEMA_MIGRATE_WAIT_SECONDS (default 60).
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
echo "migrate: done"

#!/usr/bin/env bash
# Restore a backup made by backup-postgres.sh.
#
#   restore-postgres.sh --verify  <file>            restore into a scratch database, count tables, drop it
#   restore-postgres.sh --restore <file>            restore into a NEW database (name: PEMA_RESTORE_DB)
#
# It never overwrites the live database. To go live after a disaster: stop api/worker, run --restore into
# `pema_restored`, check it, then `ALTER DATABASE pema RENAME TO pema_old; ALTER DATABASE pema_restored RENAME
# TO pema;` (nobody connected), start the services. Run --verify at least once a quarter: a backup that was
# never restored is a hope, not a backup.
#
# Decryption: PEMA_RESTORE_AGE_IDENTITY (path of the age private key) for *.age; gpg uses its own keyring.
# Same PEMA_BACKUP_COMPOSE / PEMA_BACKUP_SERVICE variables as backup-postgres.sh.
set -euo pipefail
umask 077

MODE="${1:-}"; FILE="${2:-}"
[ -n "$FILE" ] && [ -f "$FILE" ] && { [ "$MODE" = "--verify" ] || [ "$MODE" = "--restore" ]; } || {
  echo "usage: $0 --verify|--restore <backup file>" >&2; exit 64; }

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${PEMA_BACKUP_SERVICE:-postgres}"
read -r -a COMPOSE <<<"${PEMA_BACKUP_COMPOSE:-docker compose -f $INFRA/docker-compose.yml --env-file $INFRA/.env}"
if [ "$MODE" = "--verify" ]; then TARGET="pema_verify_$$"; else TARGET="${PEMA_RESTORE_DB:-pema_restored}"; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

case "$FILE" in
  *.age) age -d -i "${PEMA_RESTORE_AGE_IDENTITY:?set PEMA_RESTORE_AGE_IDENTITY}" "$FILE" | tar -C "$TMP" -xf - ;;
  *.gpg) gpg --batch --decrypt "$FILE" | tar -C "$TMP" -xf - ;;
  *)     tar -C "$TMP" -xf "$FILE" ;;
esac
[ -f "$TMP/db.dump" ] || { echo "not a Pema backup (db.dump missing)" >&2; exit 2; }

psql_in() { "${COMPOSE[@]}" exec -T "$SERVICE" psql -U postgres -v ON_ERROR_STOP=1 "$@"; }

# Roles first (be_app / agent_worker with their password hashes). "already exists" for postgres is expected.
psql_in -d postgres <"$TMP/globals.sql" >/dev/null 2>&1 || true

psql_in -d postgres -c "CREATE DATABASE \"$TARGET\"" >/dev/null
# --no-owner is NOT used: owners and GRANTs come back as dumped.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore -U postgres -d "$TARGET" --exit-on-error <"$TMP/db.dump"

TABLES="$(psql_in -d "$TARGET" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('clinic','agent','clinic_agent','ctx')")"
REV="$(psql_in -d "$TARGET" -At -c "SELECT string_agg(version_num, ',') FROM public.alembic_version_pema")"
echo "restored into $TARGET: $TABLES tables/views in clinic/agent/clinic_agent/ctx, alembic revision(s): $REV"

# One installation = one clinic: a restored database must hold exactly one clinic row.
CLINICS="$(psql_in -d "$TARGET" -At -c "SELECT count(*) FROM clinic.clinic")"
if [ "$CLINICS" != "1" ]; then
  echo "restore check failed: clinic.clinic holds $CLINICS row(s), expected exactly 1" >&2
  exit 2
fi
CLINIC_NAME="$(psql_in -d "$TARGET" -At -c "SELECT name FROM clinic.clinic")"
echo "restored clinic: $CLINIC_NAME (exactly one row)"

if [ "$MODE" = "--verify" ]; then
  psql_in -d postgres -c "DROP DATABASE \"$TARGET\"" >/dev/null
  echo "verify ok; scratch database dropped"
fi

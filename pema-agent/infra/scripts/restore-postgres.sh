#!/usr/bin/env bash
# Restore a backup made by backup-postgres.sh.
#
#   restore-postgres.sh --verify  <file>            restore into a scratch database, count tables, drop it
#   restore-postgres.sh --restore <file>            restore into a NEW database (name: PEMA_RESTORE_DB)
#                                                   and the agent's into <that name>_agent, the photos into
#                                                   /var/lib/pema/clinic-media.<that name> (api container) and
#                                                   the Zalo connector's data into /data/restored.<that name> (zalo container;
#                                                   inside its volume because its root filesystem is read-only)
#
# It never overwrites the live database or the live photos. To go live after a disaster: stop api/worker, run
# --restore into `pema_restored`, check it, then `ALTER DATABASE pema RENAME TO pema_old; ALTER DATABASE
# pema_restored RENAME TO pema;` (nobody connected), the same for `pema_agent` and `pema_restored_agent`, move
# clinic-media to clinic-media.old and clinic-media.pema_restored to clinic-media, stop `zalo` and do the same
# with the files of /data/restored.pema_restored (zalo.db into /data), start the services. Run
# --verify at least once a quarter: a backup that was never restored is a hope, not a backup.
#
# Decryption: PEMA_RESTORE_AGE_IDENTITY (path of the age private key) for *.age; gpg uses its own keyring.
# Same PEMA_BACKUP_COMPOSE / PEMA_BACKUP_SERVICE / PEMA_BACKUP_API_SERVICE / PEMA_BACKUP_ZALO_SERVICE variables as backup-postgres.sh.
set -euo pipefail
umask 077

MODE="${1:-}"; FILE="${2:-}"
[ -n "$FILE" ] && [ -f "$FILE" ] && { [ "$MODE" = "--verify" ] || [ "$MODE" = "--restore" ]; } || {
  echo "usage: $0 --verify|--restore <backup file>" >&2; exit 64; }

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${PEMA_BACKUP_SERVICE:-postgres}"
API_SERVICE="${PEMA_BACKUP_API_SERVICE:-api}"
ZALO_SERVICE="${PEMA_BACKUP_ZALO_SERVICE:-zalo}"
MEDIA_DIR=/var/lib/pema/clinic-media
ZALO_DATA_DIR=/data
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

# Roles first (be_app and the agent's role with their password hashes). "already exists" for postgres is expected.
psql_in -d postgres <"$TMP/globals.sql" >/dev/null 2>&1 || true

psql_in -d postgres -c "CREATE DATABASE \"$TARGET\"" >/dev/null
# --no-owner is NOT used: owners and GRANTs come back as dumped.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore -U postgres -d "$TARGET" --exit-on-error <"$TMP/db.dump"

TABLES="$(psql_in -d "$TARGET" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('clinic','ctx')")"
REV="$(psql_in -d "$TARGET" -At -c "SELECT string_agg(version_num, ',') FROM public.alembic_version_pema")"
echo "restored into $TARGET: $TABLES tables/views in clinic/ctx, alembic revision(s): $REV"

# One installation = one clinic: a restored database must hold exactly one clinic row.
CLINICS="$(psql_in -d "$TARGET" -At -c "SELECT count(*) FROM clinic.clinic")"
if [ "$CLINICS" != "1" ]; then
  echo "restore check failed: clinic.clinic holds $CLINICS row(s), expected exactly 1" >&2
  exit 2
fi
CLINIC_NAME="$(psql_in -d "$TARGET" -At -c "SELECT name FROM clinic.clinic")"
echo "restored clinic: $CLINIC_NAME (exactly one row)"

if [ -f "$TMP/agent.dump" ]; then
  psql_in -d postgres -c "CREATE DATABASE \"${TARGET}_agent\"" >/dev/null
  "${COMPOSE[@]}" exec -T "$SERVICE" pg_restore -U postgres -d "${TARGET}_agent" --exit-on-error <"$TMP/agent.dump"
  AGENT_TABLES="$(psql_in -d "${TARGET}_agent" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'agent_rt'")"
  echo "restored the agent into ${TARGET}_agent: $AGENT_TABLES tables in agent_rt"
fi

if [ -f "$TMP/media.tar.gz" ]; then
  # reading the whole archive checks it; --verify stops there, like the scratch database it drops
  tar -tzf "$TMP/media.tar.gz" >"$TMP/media.list"
  PHOTOS="$(grep -vc '/$' "$TMP/media.list" || true)"
  if [ "$MODE" = "--restore" ]; then
    # mkdir without -p fails when the folder exists: a restore never writes over photos already there
    "${COMPOSE[@]}" exec -T "$API_SERVICE" mkdir "$MEDIA_DIR.$TARGET"
    "${COMPOSE[@]}" exec -T "$API_SERVICE" tar -C "$MEDIA_DIR.$TARGET" -xzf - <"$TMP/media.tar.gz"
    echo "restored $PHOTOS photo file(s) into $MEDIA_DIR.$TARGET"
  else
    echo "photo archive readable: $PHOTOS file(s)"
  fi
fi

if [ -f "$TMP/zalo-data.tar.gz" ]; then
  tar -tzf "$TMP/zalo-data.tar.gz" >"$TMP/zalo.list"
  ZALO_FILES="$(grep -vc '/$' "$TMP/zalo.list" || true)"
  if [ "$MODE" = "--restore" ]; then
    # a NEW folder inside the volume (mkdir without -p fails when it exists), never over the live zalo.db
    "${COMPOSE[@]}" exec -T "$ZALO_SERVICE" mkdir "$ZALO_DATA_DIR/restored.$TARGET"
    "${COMPOSE[@]}" exec -T "$ZALO_SERVICE" tar -C "$ZALO_DATA_DIR/restored.$TARGET" -xzf - <"$TMP/zalo-data.tar.gz"
    echo "restored $ZALO_FILES Zalo connector file(s) into $ZALO_DATA_DIR/restored.$TARGET (zalo container)"
  else
    echo "zalo data archive readable: $ZALO_FILES file(s)"
  fi
fi

if [ "$MODE" = "--verify" ]; then
  psql_in -d postgres -c "DROP DATABASE \"$TARGET\"" >/dev/null
  psql_in -d postgres -c "DROP DATABASE IF EXISTS \"${TARGET}_agent\"" >/dev/null
  echo "verify ok; scratch databases dropped"
fi

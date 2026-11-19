#!/usr/bin/env bash
# Restore a backup made by backup-postgres.sh.
#
#   restore-postgres.sh --verify  <file>            restore into a scratch database, count tables, drop it
#   restore-postgres.sh --restore <file>            restore into a NEW database (name: PEMA_RESTORE_DB, default
#                                                   pema_agent_restored), the agent's home into /data/restored.<that name>
#                                                   (agent container) and the Zalo connector's data into
#                                                   /data/restored.<that name> (zalo container; inside the volumes
#                                                   because their root filesystems are read-only)
#
# It never overwrites the live database or the live files. To go live after a disaster: stop agent and zalo, run
# --restore, check it, then `ALTER DATABASE pema_agent RENAME TO pema_agent_old; ALTER DATABASE pema_agent_restored
# RENAME TO pema_agent;` (nobody connected), move the files of /data/restored.<name> into /data in the agent and the
# zalo containers, start the services. Run --verify at least once a quarter: a backup that was never restored is a
# hope, not a backup.
#
# Decryption: PEMA_RESTORE_AGE_IDENTITY (path of the age private key) for *.age; gpg uses its own keyring.
# Same PEMA_BACKUP_COMPOSE / PEMA_BACKUP_SERVICE / PEMA_BACKUP_AGENT_SERVICE / PEMA_BACKUP_ZALO_SERVICE variables as
# backup-postgres.sh.
set -euo pipefail
umask 077

MODE="${1:-}"; FILE="${2:-}"
[ -n "$FILE" ] && [ -f "$FILE" ] && { [ "$MODE" = "--verify" ] || [ "$MODE" = "--restore" ]; } || {
  echo "usage: $0 --verify|--restore <backup file>" >&2; exit 64; }

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${PEMA_BACKUP_SERVICE:-postgres}"
AGENT_SERVICE="${PEMA_BACKUP_AGENT_SERVICE:-agent}"
ZALO_SERVICE="${PEMA_BACKUP_ZALO_SERVICE:-zalo}"
AGENT_HOME=/data
ZALO_DATA_DIR=/data
read -r -a COMPOSE <<<"${PEMA_BACKUP_COMPOSE:-docker compose -f $INFRA/docker-compose.yml --env-file $INFRA/.env}"
if [ "$MODE" = "--verify" ]; then TARGET="agent_verify_$$"; else TARGET="${PEMA_RESTORE_DB:-pema_agent_restored}"; fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

case "$FILE" in
  *.age) age -d -i "${PEMA_RESTORE_AGE_IDENTITY:?set PEMA_RESTORE_AGE_IDENTITY}" "$FILE" | tar -C "$TMP" -xf - ;;
  *.gpg) gpg --batch --decrypt "$FILE" | tar -C "$TMP" -xf - ;;
  *)     tar -C "$TMP" -xf "$FILE" ;;
esac
[ -f "$TMP/agent.dump" ] || { echo "not an agent backup (agent.dump missing)" >&2; exit 2; }

psql_in() { "${COMPOSE[@]}" exec -T "$SERVICE" psql -U postgres -v ON_ERROR_STOP=1 "$@"; }

# Roles first (the agent's role with its password hash). "already exists" for postgres is expected.
psql_in -d postgres <"$TMP/globals.sql" >/dev/null 2>&1 || true

psql_in -d postgres -c "CREATE DATABASE \"$TARGET\"" >/dev/null
# --no-owner is NOT used: owners and GRANTs come back as dumped.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore -U postgres -d "$TARGET" --exit-on-error <"$TMP/agent.dump"
AGENT_TABLES="$(psql_in -d "$TARGET" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'agent_rt'")"
echo "restored the agent into $TARGET: $AGENT_TABLES tables in agent_rt"

if [ -f "$TMP/agent-home.tar.gz" ]; then
  tar -tzf "$TMP/agent-home.tar.gz" >"$TMP/home.list"
  HOME_FILES="$(grep -vc '/$' "$TMP/home.list" || true)"
  if [ "$MODE" = "--restore" ]; then
    # a NEW folder inside the volume (mkdir without -p fails when it exists), never over the live secret key
    "${COMPOSE[@]}" exec -T "$AGENT_SERVICE" mkdir "$AGENT_HOME/restored.$TARGET"
    "${COMPOSE[@]}" exec -T "$AGENT_SERVICE" tar -C "$AGENT_HOME/restored.$TARGET" -xzf - <"$TMP/agent-home.tar.gz"
    echo "restored $HOME_FILES agent home file(s) into $AGENT_HOME/restored.$TARGET (agent container)"
  else
    echo "agent home archive readable: $HOME_FILES file(s)"
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
  echo "verify ok; scratch database dropped"
fi

#!/usr/bin/env bash
# Logical backup of the agent: one custom-format dump of `pema_agent` + the cluster's roles (globals) + the agent's
# home (/data of the agent container: its secret key, which seals the model keys in the database, and the installed
# plugins) + the Zalo connector's /data (when it runs), verified, encrypted, with simple retention. Run from the host
# that runs docker compose (cron or the systemd timer in infra/ubuntu/systemd).
#
# The dump holds conversations, contacts and sealed keys. It is therefore ENCRYPTED
# unless you explicitly allow plaintext for a throwaway test:
#   CONTETE_BACKUP_AGE_RECIPIENT   age public key (preferred: only the public key lives on the server; keep the
#                               private key off the server, e.g. a password manager and a sealed printout)
#   CONTETE_BACKUP_GPG_RECIPIENT   gpg key id or e-mail (alternative to age)
#   CONTETE_BACKUP_ALLOW_PLAINTEXT true to skip encryption (tests only)
#
# Other variables (all optional):
#   CONTETE_BACKUP_DIR             where files go (default /var/backups/contete-agent; use another disk or a mounted share)
#   CONTETE_BACKUP_KEEP_DAYS       delete our files older than this (default 14)
#   CONTETE_BACKUP_COMPOSE         the compose command (default: docker compose -f <infra>/docker-compose.yml --env-file <infra>/.env)
#   CONTETE_BACKUP_SERVICE         compose service name of Postgres (default postgres)
#   CONTETE_BACKUP_AGENT_DB        the agent's database (default pema_agent)
#   CONTETE_BACKUP_AGENT_SERVICE   compose service name of the agent, which holds its home in /data (default agent)
#   CONTETE_BACKUP_ZALO_SERVICE    compose service name of the Zalo connector, which holds /data/zalo.db (accounts, sealed
#                               tokens, the inbound outbox; default zalo; skipped when that service is not running)
#   CONTETE_BACKUP_HOOK            command run with the finished file path as $1 (rsync/rclone to the second site)
#
# Exit codes: 0 ok; non-zero on any failure (cron mails stderr). Nothing is printed except file names and sizes.
set -euo pipefail
umask 077

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${CONTETE_BACKUP_DIR:-/var/backups/contete-agent}"
KEEP="${CONTETE_BACKUP_KEEP_DAYS:-14}"
SERVICE="${CONTETE_BACKUP_SERVICE:-postgres}"
AGENT_DB="${CONTETE_BACKUP_AGENT_DB:-pema_agent}"
AGENT_SERVICE="${CONTETE_BACKUP_AGENT_SERVICE:-agent}"
ZALO_SERVICE="${CONTETE_BACKUP_ZALO_SERVICE:-zalo}"
# the agent's home (docker-compose.yml, volume agent-home)
AGENT_HOME=/data
# the Zalo connector's volume (docker-compose.yml, service zalo)
ZALO_DATA_DIR=/data
read -r -a COMPOSE <<<"${CONTETE_BACKUP_COMPOSE:-docker compose -f $INFRA/docker-compose.yml --env-file $INFRA/.env}"

encrypt() { # stdin -> stdout
  if [ -n "${CONTETE_BACKUP_AGE_RECIPIENT:-}" ]; then
    age -r "$CONTETE_BACKUP_AGE_RECIPIENT"
  elif [ -n "${CONTETE_BACKUP_GPG_RECIPIENT:-}" ]; then
    gpg --batch --yes --encrypt --recipient "$CONTETE_BACKUP_GPG_RECIPIENT"
  elif [ "${CONTETE_BACKUP_ALLOW_PLAINTEXT:-false}" = "true" ]; then
    cat
  else
    echo "no encryption configured: set CONTETE_BACKUP_AGE_RECIPIENT or CONTETE_BACKUP_GPG_RECIPIENT" >&2
    return 1
  fi
}

SUFFIX=""
if [ -n "${CONTETE_BACKUP_AGE_RECIPIENT:-}" ]; then SUFFIX=".age"
elif [ -n "${CONTETE_BACKUP_GPG_RECIPIENT:-}" ]; then SUFFIX=".gpg"; fi

# Fail before touching the database when no encryption is configured.
if [ -z "$SUFFIX" ] && [ "${CONTETE_BACKUP_ALLOW_PLAINTEXT:-false}" != "true" ]; then
  echo "no encryption configured: set CONTETE_BACKUP_AGE_RECIPIENT or CONTETE_BACKUP_GPG_RECIPIENT" >&2
  exit 1
fi

mkdir -p "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/backup-$STAMP.tar$SUFFIX"
TMP="$(mktemp -d "$DIR/.tmp.XXXXXX")"
# a failed run leaves neither the temp dir nor a half-written file behind
trap 'rm -rf "$TMP" "$OUT.part"' EXIT

# 1. Dump inside the container as the superuser (local socket, no password in our argv). Owners and GRANTs
#    stay in the archive (no --no-owner / --no-privileges): the role split and the grants depend on them.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_dump -U postgres -Fc "$AGENT_DB" >"$TMP/agent.dump"
"${COMPOSE[@]}" exec -T "$SERVICE" pg_dumpall -U postgres --globals-only >"$TMP/globals.sql"
FILES=(agent.dump globals.sql)
# The agent's home: without its secret key the model keys sealed in the database cannot be read. A stopped agent
# fails the backup instead of silently leaving it out.
"${COMPOSE[@]}" exec -T "$AGENT_SERVICE" tar -C "$AGENT_HOME" -czf - . >"$TMP/agent-home.tar.gz"
FILES+=(agent-home.tar.gz)
# The Zalo connector's data (zalo.db: accounts, sealed tokens, the inbound outbox). A stack without the connector (not
# started) is fine: skip with a line, never fail. shortcut: tar of the live /data, so a
# write during the second of the copy can leave zalo.db a few rows behind (the outbox is retried by the connector);
# upgrade to a sqlite3 .backup snapshot if that ever matters.
if [ -n "$("${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -Fx "$ZALO_SERVICE" || true)" ]; then
  "${COMPOSE[@]}" exec -T "$ZALO_SERVICE" tar -C "$ZALO_DATA_DIR" -czf - . >"$TMP/zalo-data.tar.gz"
  FILES+=(zalo-data.tar.gz)
else
  echo "zalo service '$ZALO_SERVICE' is not running: its data is not in this backup"
fi

# 2. Verify before trusting it: pg_restore must be able to list the archive and it must contain the agent's schema.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore --list <"$TMP/agent.dump" | grep -q " SCHEMA - agent_rt " ||
  { echo "backup check failed: schema agent_rt missing in $AGENT_DB" >&2; exit 2; }

# 3. Bundle and encrypt. tar keeps the files in one object so a restore cannot mix dates.
tar -C "$TMP" -cf - "${FILES[@]}" | encrypt >"$OUT.part"
mv "$OUT.part" "$OUT"
echo "backup written: $OUT ($(wc -c <"$OUT") bytes)"

# 4. Retention: only our own files.
find "$DIR" -maxdepth 1 -type f -name 'backup-*.tar*' -mtime "+$KEEP" -print -delete

# 5. Off-site copy hook (second disk, another machine over Tailscale, a VN cloud bucket).
if [ -n "${CONTETE_BACKUP_HOOK:-}" ]; then
  # shellcheck disable=SC2086
  $CONTETE_BACKUP_HOOK "$OUT"
fi

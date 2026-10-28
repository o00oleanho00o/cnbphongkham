#!/usr/bin/env bash
# Logical backup of the Pema databases: one custom-format dump of `pema` (the clinic), one of `pema_agent` (the
# agent, when it exists) + the cluster's roles (globals) + the clinic photos (from the api container) + the Zalo
# connector's /data (from the zalo container, when it runs), verified, encrypted, with simple retention. One installation = one clinic = one database, so the dump is the
# WHOLE clinic (every patient, message and credential it has); treat it with that weight. A second clinic has its
# own stack and must use its own PEMA_BACKUP_DIR and its own age key. Run from the host that runs docker compose
# (cron or the systemd timer in infra/ubuntu/systemd).
#
# The dump holds patient data (synthetic in this repository, real in a clinic). It is therefore ENCRYPTED
# unless you explicitly allow plaintext for a throwaway test:
#   PEMA_BACKUP_AGE_RECIPIENT   age public key (preferred: only the public key lives on the server; keep the
#                               private key off the server, e.g. a password manager and a sealed printout)
#   PEMA_BACKUP_GPG_RECIPIENT   gpg key id or e-mail (alternative to age)
#   PEMA_BACKUP_ALLOW_PLAINTEXT true to skip encryption (tests only)
#
# Other variables (all optional):
#   PEMA_BACKUP_DIR             where files go (default /var/backups/pema; use another disk or a mounted share)
#   PEMA_BACKUP_KEEP_DAYS       delete our files older than this (default 14)
#   PEMA_BACKUP_COMPOSE         the compose command (default: docker compose -f <infra>/docker-compose.yml --env-file <infra>/.env)
#   PEMA_BACKUP_SERVICE         compose service name of Postgres (default postgres)
#   PEMA_BACKUP_DB              database (default pema)
#   PEMA_BACKUP_AGENT_DB        the agent's database (default pema_agent; skipped when the server has none)
#   PEMA_BACKUP_API_SERVICE     compose service name of the API, which holds the clinic photos (default api)
#   PEMA_BACKUP_ZALO_SERVICE    compose service name of the Zalo connector, which holds /data/zalo.db (accounts, sealed
#                               tokens, the inbound outbox; default zalo; skipped when that service is not running)
#   PEMA_BACKUP_HOOK            command run with the finished file path as $1 (rsync/rclone to the second site)
#
# Exit codes: 0 ok; non-zero on any failure (cron mails stderr). Nothing is printed except file names and sizes.
set -euo pipefail
umask 077

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${PEMA_BACKUP_DIR:-/var/backups/pema}"
KEEP="${PEMA_BACKUP_KEEP_DAYS:-14}"
SERVICE="${PEMA_BACKUP_SERVICE:-postgres}"
DB="${PEMA_BACKUP_DB:-pema}"
AGENT_DB="${PEMA_BACKUP_AGENT_DB:-pema_agent}"
API_SERVICE="${PEMA_BACKUP_API_SERVICE:-api}"
ZALO_SERVICE="${PEMA_BACKUP_ZALO_SERVICE:-zalo}"
# the photos of the Ảnh trước / sau tab: <PEMA_DATA_DIR>/clinic-media on the pema-data volume (docker-compose.yml)
MEDIA_DIR=/var/lib/pema/clinic-media
# the Zalo connector's volume (docker-compose.yml, service zalo)
ZALO_DATA_DIR=/data
read -r -a COMPOSE <<<"${PEMA_BACKUP_COMPOSE:-docker compose -f $INFRA/docker-compose.yml --env-file $INFRA/.env}"

encrypt() { # stdin -> stdout
  if [ -n "${PEMA_BACKUP_AGE_RECIPIENT:-}" ]; then
    age -r "$PEMA_BACKUP_AGE_RECIPIENT"
  elif [ -n "${PEMA_BACKUP_GPG_RECIPIENT:-}" ]; then
    gpg --batch --yes --encrypt --recipient "$PEMA_BACKUP_GPG_RECIPIENT"
  elif [ "${PEMA_BACKUP_ALLOW_PLAINTEXT:-false}" = "true" ]; then
    cat
  else
    echo "no encryption configured: set PEMA_BACKUP_AGE_RECIPIENT or PEMA_BACKUP_GPG_RECIPIENT" >&2
    return 1
  fi
}

SUFFIX=""
if [ -n "${PEMA_BACKUP_AGE_RECIPIENT:-}" ]; then SUFFIX=".age"
elif [ -n "${PEMA_BACKUP_GPG_RECIPIENT:-}" ]; then SUFFIX=".gpg"; fi

# Fail before touching the database when no encryption is configured.
if [ -z "$SUFFIX" ] && [ "${PEMA_BACKUP_ALLOW_PLAINTEXT:-false}" != "true" ]; then
  echo "no encryption configured: set PEMA_BACKUP_AGE_RECIPIENT or PEMA_BACKUP_GPG_RECIPIENT" >&2
  exit 1
fi

mkdir -p "$DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DIR/pema-$STAMP.tar$SUFFIX"
TMP="$(mktemp -d "$DIR/.tmp.XXXXXX")"
# a failed run leaves neither the temp dir nor a half-written file behind
trap 'rm -rf "$TMP" "$OUT.part"' EXIT

# 1. Dump inside the container as the superuser (local socket, no password in our argv). Owners and GRANTs
#    stay in the archive (no --no-owner / --no-privileges): the role split and the grants depend on them.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_dump -U postgres -Fc "$DB" >"$TMP/db.dump"
"${COMPOSE[@]}" exec -T "$SERVICE" pg_dumpall -U postgres --globals-only >"$TMP/globals.sql"
FILES=(db.dump globals.sql)
if [ "$("${COMPOSE[@]}" exec -T "$SERVICE" psql -U postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$AGENT_DB'")" = "1" ]; then
  "${COMPOSE[@]}" exec -T "$SERVICE" pg_dump -U postgres -Fc "$AGENT_DB" >"$TMP/agent.dump"
  "${COMPOSE[@]}" exec -T "$SERVICE" pg_restore --list <"$TMP/agent.dump" | grep -q " SCHEMA - agent_rt " ||
    { echo "backup check failed: schema agent_rt missing in $AGENT_DB" >&2; exit 2; }
  FILES+=(agent.dump)
fi
# The photos go into the same archive as the rows that point at them (same date, same encryption). mkdir -p: the
# folder appears only with the first upload; a stopped api fails the backup instead of silently leaving them out.
"${COMPOSE[@]}" exec -T "$API_SERVICE" mkdir -p "$MEDIA_DIR"
"${COMPOSE[@]}" exec -T "$API_SERVICE" tar -C "$MEDIA_DIR" -czf - . >"$TMP/media.tar.gz"
FILES+=(media.tar.gz)
# The Zalo connector's data (zalo.db: accounts, sealed tokens, the inbound outbox). A stack without the connector (no
# profile `agent`, or not started) is fine: skip with a line, never fail. shortcut: tar of the live /data, so a
# write during the second of the copy can leave zalo.db a few rows behind (the outbox is retried by the connector);
# upgrade to a sqlite3 .backup snapshot if that ever matters.
if [ -n "$("${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -Fx "$ZALO_SERVICE" || true)" ]; then
  "${COMPOSE[@]}" exec -T "$ZALO_SERVICE" tar -C "$ZALO_DATA_DIR" -czf - . >"$TMP/zalo-data.tar.gz"
  FILES+=(zalo-data.tar.gz)
else
  echo "zalo service '$ZALO_SERVICE' is not running: its data is not in this backup"
fi

# 2. Verify before trusting it: pg_restore must be able to list the archive and it must contain the schemas.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore --list <"$TMP/db.dump" >"$TMP/db.list"
for schema in clinic ctx; do
  grep -q " SCHEMA - $schema " "$TMP/db.list" || { echo "backup check failed: schema $schema missing" >&2; exit 2; }
done
# the installation's clinic row must be in the archive (restoring without it would leave an unusable system)
grep -q " TABLE DATA clinic clinic " "$TMP/db.list" || { echo "backup check failed: clinic.clinic data missing" >&2; exit 2; }

# 3. Bundle and encrypt. tar keeps the files in one object so a restore cannot mix dates.
tar -C "$TMP" -cf - "${FILES[@]}" | encrypt >"$OUT.part"
mv "$OUT.part" "$OUT"
echo "backup written: $OUT ($(wc -c <"$OUT") bytes)"

# 4. Retention: only our own files.
find "$DIR" -maxdepth 1 -type f -name 'pema-*.tar*' -mtime "+$KEEP" -print -delete

# 5. Off-site copy hook (second disk, another machine over Tailscale, a VN cloud bucket).
if [ -n "${PEMA_BACKUP_HOOK:-}" ]; then
  # shellcheck disable=SC2086
  $PEMA_BACKUP_HOOK "$OUT"
fi

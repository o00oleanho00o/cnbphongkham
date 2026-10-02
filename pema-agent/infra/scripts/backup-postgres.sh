#!/usr/bin/env bash
# Logical backup of the Pema database: one custom-format dump of `pema` + the cluster's roles (globals),
# verified, encrypted, with simple retention. One installation = one clinic = one database, so the dump is the
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

# 2. Verify before trusting it: pg_restore must be able to list the archive and it must contain the schemas.
"${COMPOSE[@]}" exec -T "$SERVICE" pg_restore --list <"$TMP/db.dump" >"$TMP/db.list"
for schema in clinic agent clinic_agent; do
  grep -q " SCHEMA - $schema " "$TMP/db.list" || { echo "backup check failed: schema $schema missing" >&2; exit 2; }
done
# the installation's clinic row must be in the archive (restoring without it would leave an unusable system)
grep -q " TABLE DATA clinic clinic " "$TMP/db.list" || { echo "backup check failed: clinic.clinic data missing" >&2; exit 2; }

# 3. Bundle and encrypt. tar keeps both files in one object so a restore cannot mix dates.
tar -C "$TMP" -cf - db.dump globals.sql | encrypt >"$OUT.part"
mv "$OUT.part" "$OUT"
echo "backup written: $OUT ($(wc -c <"$OUT") bytes)"

# 4. Retention: only our own files.
find "$DIR" -maxdepth 1 -type f -name 'pema-*.tar*' -mtime "+$KEEP" -print -delete

# 5. Off-site copy hook (second disk, another machine over Tailscale, a VN cloud bucket).
if [ -n "${PEMA_BACKUP_HOOK:-}" ]; then
  # shellcheck disable=SC2086
  $PEMA_BACKUP_HOOK "$OUT"
fi

#!/usr/bin/env bash
# Create infra/.env from infra/.env.example with fresh random secrets in place of every `change-me-*`
# placeholder, plus the JWT secret. Refuses to overwrite an existing .env.
#
#   infra/scripts/gen-secrets.sh            # writes infra/.env (mode 600)
#
# Passwords are lowercase hex on purpose: they are embedded in connection URLs, so no character may need
# escaping. The same placeholder gets the same value everywhere (the URLs and the plain variables agree).
# Back the resulting file up OFFLINE (password manager). The agent's own secret key (model keys) lives in the
# agent-home volume: back that up with the database. PEMA_ZALO_SECRET_KEY (Zalo tokens) is in this file.
# ZALO_CONNECTOR_KEY is not generated: the agent issues it (Connectors page).
set -euo pipefail

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$INFRA/.env.example"
DST="${1:-$INFRA/.env}"

[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }
if [ -e "$DST" ]; then
  echo "refusing to overwrite $DST (delete it first if you really want new secrets)" >&2
  exit 1
fi

rand_hex() { openssl rand -hex "$1"; }

umask 077
cp "$SRC" "$DST"

# `|| true`: grep exits 1 when the file has no placeholder left.
# The Zalo seal key is a Fernet-style key (32 random bytes, urlsafe base64), not hex: set it first, the placeholder
# loop below would otherwise turn it into hex.
sed -i "s|^PEMA_ZALO_SECRET_KEY=.*|PEMA_ZALO_SECRET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')|" "$DST"
for token in $(grep -o 'change-me-[a-z0-9-]*' "$SRC" | sort -u || true); do
  sed -i "s|${token}|$(rand_hex 24)|g" "$DST"
done
sed -i "s|^PEMA_JWT_SECRET=.*|PEMA_JWT_SECRET=$(rand_hex 32)|" "$DST"
chmod 600 "$DST"

echo "wrote $DST (not tracked by git). Review it, then: make up"

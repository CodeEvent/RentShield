#!/usr/bin/env bash
# Starts the RentShield demo server each time the Codespace starts.
# PAPERLESS_AUTO_LOGIN_USERNAME logs every visitor straight in as the demo
# Property Owner (no OTP, no password) -- correct ONLY for this throwaway
# public demo, never for production. The Codespace's own forwarded HTTPS
# host is wired into ALLOWED_HOSTS / CSRF so the Angular app's API calls work.
set -euo pipefail
cd "${CODESPACE_VSCODE_FOLDER:-$(cd "$(dirname "$0")/.." && pwd)}"
export PATH="$HOME/.local/bin:$PATH"

HOST="${CODESPACE_NAME:-localhost}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
export PAPERLESS_AUTO_LOGIN_USERNAME=demo
export PAPERLESS_URL="https://${HOST}"
export PAPERLESS_ALLOWED_HOSTS="${HOST},localhost,127.0.0.1"
export PAPERLESS_CSRF_TRUSTED_ORIGINS="https://${HOST}"

cd src
pkill -f "manage.py runserver" 2>/dev/null || true
nohup uv run python manage.py runserver 0.0.0.0:8000 > /tmp/rentshield-server.log 2>&1 &

echo "RentShield demo starting at: https://${HOST}"
echo "(server log: /tmp/rentshield-server.log)"

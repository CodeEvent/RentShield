#!/usr/bin/env bash
# One-time setup for the free GitHub Codespaces demo of RentShield.
# Installs Python + JS deps, builds the Angular frontend, writes a demo
# (sqlite, DEBUG) config, migrates, seeds the role groups + workflows, and
# seeds the demo account/identity/notices. Safe to re-run.
set -euo pipefail
cd "${CODESPACE_VSCODE_FOLDER:-$(cd "$(dirname "$0")/.." && pwd)}"
export PATH="$HOME/.local/bin:$PATH"

echo "[setup] system libraries (python-magic, opencv runtime)"
sudo apt-get update -y || true
sudo apt-get install -y libmagic1 libgl1 >/dev/null 2>&1 || true

echo "[setup] uv + Python dependencies (this takes a few minutes)"
command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
export UV_HTTP_TIMEOUT=900
uv sync

# NOTE: the PDF renderer (Playwright/Chromium) is deliberately NOT installed
# here -- it is heavy and only needed to render notice/handoff PDFs. The demo
# seed falls back to metadata-only notices without it, so every data tab still
# populates; the "download PDF" / handoff buttons simply won't produce a file.

echo "[setup] build the Angular frontend"
corepack enable || true
( cd src-ui && corepack pnpm install \
  && NODE_OPTIONS=--max-old-space-size=4096 corepack pnpm build )
rm -rf src/documents/static/frontend
cp -r src-ui/dist/paperless-ui src/documents/static/frontend

echo "[setup] demo config (sqlite, DEBUG -- a throwaway demo, NOT production)"
cat > paperless.conf <<'CONF'
PAPERLESS_DEBUG=true
PAPERLESS_SECRET_KEY=demo-only-not-a-secret
PAPERLESS_DBENGINE=sqlite
PAPERLESS_TIME_ZONE=Asia/Dubai
CONF

echo "[setup] migrate, seed roles/workflows, seed demo data"
cd src
uv run python manage.py migrate --no-input
uv run python manage.py create_rentshield_roles
uv run python manage.py create_rentshield_workflows || true
uv run python manage.py seed_rentshield_demo
echo "[setup] done -- the server starts automatically (see start.sh)"

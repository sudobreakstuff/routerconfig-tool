#!/bin/bash
# Build the production desktop app for the current platform.
#   Linux:   AppImage + deb
#   Windows: NSIS installer
# Requires: Python 3.10+ venv with backend deps installed, Node.js + npm.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

echo "==> [1/3] Bundling backend into a self-contained binary"
if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "    creating backend venv"
  "$PYTHON" -m venv "$ROOT/backend/.venv"
fi
"$ROOT/backend/.venv/bin/pip" install -q -e "$ROOT/backend" pyinstaller

(
  cd "$ROOT/backend"
  rm -rf build dist
  .venv/bin/pyinstaller routerconfig-backend.spec --noconfirm --clean >/dev/null
)
echo "    backend bundle: $ROOT/backend/dist/routerconfig-backend"

echo "==> [2/3] Installing frontend dependencies"
cd "$ROOT/frontend"
npm install --no-audit --no-fund >/dev/null

echo "==> [3/3] Building Electron app"
npm run electron:build

echo ""
echo "Done. Artifacts:"
ls -1 "$ROOT/frontend/dist/" | grep -E "\.(AppImage|deb|exe)$" || echo "  (none found in frontend/dist)"

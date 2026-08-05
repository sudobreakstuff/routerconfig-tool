#!/bin/bash
# Build the production desktop app (AppImage + deb on Linux, NSIS on Windows).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building frontend + backend into distributable"
cd "$ROOT/frontend"
npm run electron:build

echo ""
echo "Done. Artifacts are in frontend/dist/*.AppImage / *.deb (or dist/*.exe on Windows)."

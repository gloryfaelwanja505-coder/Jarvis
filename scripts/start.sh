#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Backend is not installed. Run ./scripts/install.sh first." >&2
  exit 1
fi
if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
  echo "Frontend is not installed. Run ./scripts/install.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR/backend"
"$ROOT_DIR/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
(
  cd "$ROOT_DIR/frontend"
  npm run dev -- --host 127.0.0.1
) &
FRONTEND_PID=$!

cleanup() {
  kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait "$BACKEND_PID" "$FRONTEND_PID"

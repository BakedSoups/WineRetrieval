#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Stopping frontend container..."
docker compose stop frontend >/dev/null 2>&1 || true

if [ -f .backend.pid ]; then
  BACKEND_PID="$(cat .backend.pid)"
  if kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Stopping backend PID $BACKEND_PID..."
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  rm -f .backend.pid
fi

echo "Stopped."


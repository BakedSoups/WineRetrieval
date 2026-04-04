#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -f .backend.pid ] && kill -0 "$(cat .backend.pid)" 2>/dev/null; then
  echo "Backend already running with PID $(cat .backend.pid)"
else
  echo "Starting backend on host..."
  python app.py > backend.log 2>&1 &
  echo $! > .backend.pid
  echo "Backend started with PID $(cat .backend.pid)"
fi

echo "Starting frontend in Docker..."
docker compose up --build -d frontend

echo
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "Backend logs: tail -f backend.log"


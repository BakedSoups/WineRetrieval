#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/react_app"
LOG_DIR="$ROOT_DIR/.run"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3001}"

mkdir -p "$LOG_DIR"

if [[ ! -f "$ROOT_DIR/app.py" ]]; then
  echo "Missing backend entrypoint: $ROOT_DIR/app.py" >&2
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Missing frontend app: $FRONTEND_DIR/package.json" >&2
  exit 1
fi

if [[ -d "$ROOT_DIR/venv" && -x "$ROOT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/venv/bin/python"
else
  PYTHON_BIN="python3"
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Frontend dependencies are missing. Run 'npm install' in $FRONTEND_DIR first." >&2
  exit 1
fi

if [[ -f "$BACKEND_PID_FILE" ]] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
  echo "Backend already running with PID $(cat "$BACKEND_PID_FILE")" >&2
  exit 1
fi

if [[ -f "$FRONTEND_PID_FILE" ]] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; then
  echo "Frontend already running with PID $(cat "$FRONTEND_PID_FILE")" >&2
  exit 1
fi

rm -f "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"
rm -f "$FRONTEND_DIR/.next/dev/lock"

(
  cd "$ROOT_DIR"
  nohup "$PYTHON_BIN" app.py >"$BACKEND_LOG" 2>&1 &
  echo $! >"$BACKEND_PID_FILE"
)

(
  cd "$FRONTEND_DIR"
  nohup npm run dev -- --port "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PID_FILE"
)

echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo "Backend log:  $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"

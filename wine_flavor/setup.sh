#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/react_app"
VENV_DIR="$ROOT_DIR/venv"

if [[ ! -f "$ROOT_DIR/requirements.txt" ]]; then
  echo "Missing backend requirements file: $ROOT_DIR/requirements.txt" >&2
  exit 1
fi

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Missing frontend package.json: $FRONTEND_DIR/package.json" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not installed." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not installed." >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT_DIR/requirements.txt"

(
  cd "$FRONTEND_DIR"
  npm install
)

cat <<EOF
Setup complete.

Backend venv: $VENV_DIR
Frontend:     $FRONTEND_DIR

Next steps:
  cd $ROOT_DIR
  ./start_demo.sh
EOF

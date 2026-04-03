#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT_DIR/compose.yml"

resolve_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return
  fi

  echo "Docker Compose is required but was not found." >&2
  exit 1
}

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing Docker Compose file: $COMPOSE_FILE" >&2
  exit 1
fi

COMPOSE_CMD="$(resolve_compose)"

cd "$ROOT_DIR"
$COMPOSE_CMD -f "$COMPOSE_FILE" down

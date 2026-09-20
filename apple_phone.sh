#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$REPO_DIR/.env"
VENV="$REPO_DIR/.venv"
LOG="$REPO_DIR/apple_phone.log"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Missing $CONFIG_FILE. Copy .env.example to .env and set your values." >&2
  exit 1
fi

set -a
source "$CONFIG_FILE"
set +a

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Missing Python environment at $VENV. See README.md for setup." >&2
  exit 1
fi

{
  echo "[$(date)] apple_phone.sh start"
  "$VENV/bin/python" "$REPO_DIR/apple_checker_persistent.py"
  echo "[$(date)] apple_phone.sh done"
  echo
} >> "$LOG" 2>&1

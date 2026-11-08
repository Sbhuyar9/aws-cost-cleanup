#!/usr/bin/env bash
# Shared setup for the wrapper scripts: strict mode, repo root, venv, logging, lock.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-$REPO_DIR/logs}"
mkdir -p "$LOG_DIR"

# Use the project venv if present, otherwise whatever python3 is on PATH.
if [[ -f "$REPO_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_DIR/.venv/bin/activate"
fi

cd "$REPO_DIR"

log() { echo "$(date -u +'%Y-%m-%dT%H:%M:%SZ') [$(basename "$0")] $*"; }

# Prevent overlapping runs (e.g. a slow run still going when cron fires again).
acquire_lock() {
  exec 9>"/tmp/aws-cleanup-$(basename "$0").lock"
  if ! flock -n 9; then
    log "another run is in progress, exiting"
    exit 0
  fi
}

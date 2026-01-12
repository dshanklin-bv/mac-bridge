#!/bin/bash
# tosh daemon runner
# Called by launchd every 15 minutes
# Runs modular commands in sequence - each can fail independently

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOSH_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.local/log"
LOCK_FILE="$HOME/.local/run/tosh-daemon.lock"

# Ensure directories exist
mkdir -p "$LOG_DIR" "$(dirname "$LOCK_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# PID-based locking with stale detection
acquire_lock() {
    if [[ -f "$LOCK_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
        if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
            log "ERROR: Another instance running (PID $old_pid)"
            exit 1
        else
            log "WARN: Removing stale lock (PID $old_pid)"
            rm -f "$LOCK_FILE"
        fi
    fi
    echo $$ > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

trap release_lock EXIT

# Main
log "=== tosh daemon starting ==="

acquire_lock

# Check tunnel is up (localhost:15432 should be listening)
if ! nc -z localhost 15432 2>/dev/null; then
    log "ERROR: SSH tunnel not available (localhost:15432)"
    exit 2
fi

# Run sync (all sources)
log "Running: tosh sync"
if python3 -m tosh.cli.sync --source all 2>&1; then
    log "Sync completed successfully"
else
    log "WARN: Sync failed with exit code $?"
fi

# Check inbox for assignments
log "Running: tosh check-inbox"
if python3 -m tosh.cli.inbox 2>&1; then
    log "Inbox check completed"
else
    log "WARN: Inbox check failed with exit code $?"
fi

log "=== tosh daemon complete ==="
exit 0

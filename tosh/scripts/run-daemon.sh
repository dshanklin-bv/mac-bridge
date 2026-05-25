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

# Run sync (all sources - metadata only)
log "Running: tosh sync"
if python3 -m tosh.cli.sync --source all 2>&1; then
    log "Sync completed successfully"
else
    log "WARN: Sync failed with exit code $?"
fi

# Transfer local photos to server (fast operation)
log "Running: tosh photos transfer"
if python3 -m tosh.cli.photos transfer 2>&1; then
    log "Photo transfer completed"
else
    log "WARN: Photo transfer failed with exit code $?"
fi

# Download batch of iCloud photos with human-like randomization
# - Session simulation (active periods vs gaps)
# - Rest days (~8%) and burst days (~10%)
# - Daily soft cap (slows down after 2000, stops at 4000)
# - Time of day and weekend awareness
# - Random delays and occasional skips
DOWNLOAD_DECISION=$(python3 -c "from tosh.utils.humanize import should_download; ok, reason = should_download(); print(f'{ok}|{reason}')")
SHOULD_DOWNLOAD=$(echo "$DOWNLOAD_DECISION" | cut -d'|' -f1)
SKIP_REASON=$(echo "$DOWNLOAD_DECISION" | cut -d'|' -f2)

if [[ "$SHOULD_DOWNLOAD" == "False" ]]; then
    log "Skipping iCloud download: $SKIP_REASON"
else
    BATCH_SIZE=$(python3 -c "from tosh.utils.humanize import batch_size; print(batch_size())")
    DELAY=$(python3 -c "from tosh.utils.humanize import delay_seconds; print(delay_seconds())")
    DAILY_VOL=$(python3 -c "from tosh.utils.humanize import get_daily_volume; print(get_daily_volume())")

    log "Running: tosh photos download (batch=$BATCH_SIZE, delay=${DELAY}s, today=$DAILY_VOL)"
    sleep "$DELAY"

    if python3 -m tosh.cli.photos download --limit "$BATCH_SIZE" --batch-size "$BATCH_SIZE" 2>&1; then
        # Track volume for daily cap
        python3 -c "from tosh.utils.humanize import add_daily_volume; add_daily_volume($BATCH_SIZE)"
        log "iCloud download completed"
    else
        log "WARN: iCloud download failed with exit code $?"
    fi
fi

# Check inbox for assignments
log "Running: tosh check-inbox"
if python3 -m tosh.cli.inbox 2>&1; then
    log "Inbox check completed"
else
    log "WARN: Inbox check failed with exit code $?"
fi

# Report health to argus.agent_health
log "Running: tosh health report"
if python3 -m tosh.cli.health --report 2>&1; then
    log "Health reported successfully"
else
    log "WARN: Health report failed with exit code $?"
fi

# Heartbeat to Uptime Kuma (alerts user if tosh goes down)
curl -s "https://status.meetrhea.com/api/push/po1BvRj2At?status=up&msg=OK" > /dev/null || true

log "=== tosh daemon complete ==="
exit 0

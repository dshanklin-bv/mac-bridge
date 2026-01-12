#!/bin/bash
# Install tosh daemon and tunnel LaunchAgents

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOSH_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_DIR="$TOSH_DIR/plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "=== Installing tosh LaunchAgents ==="

# Create directories
mkdir -p "$LAUNCH_AGENTS"
mkdir -p "$HOME/.local/log"
mkdir -p "$HOME/.local/run"

# Copy plist files
echo "Installing com.tosh.tunnel.plist..."
cp "$PLIST_DIR/com.tosh.tunnel.plist" "$LAUNCH_AGENTS/"

echo "Installing com.tosh.daemon.plist..."
cp "$PLIST_DIR/com.tosh.daemon.plist" "$LAUNCH_AGENTS/"

# Load tunnel first (daemon depends on it)
echo "Loading tunnel..."
launchctl load "$LAUNCH_AGENTS/com.tosh.tunnel.plist" 2>/dev/null || true
launchctl start com.tosh.tunnel 2>/dev/null || true

# Wait for tunnel to establish
echo "Waiting for tunnel..."
sleep 3

# Load daemon
echo "Loading daemon..."
launchctl load "$LAUNCH_AGENTS/com.tosh.daemon.plist" 2>/dev/null || true

echo ""
echo "=== Installation complete ==="
echo ""
echo "Status:"
launchctl list | grep com.tosh || echo "  (not yet running)"
echo ""
echo "Logs:"
echo "  Tunnel: ~/.local/log/tosh-tunnel.log"
echo "  Daemon: ~/.local/log/tosh-daemon.log"
echo ""
echo "To run daemon manually:"
echo "  $TOSH_DIR/scripts/run-daemon.sh"

#!/bin/bash
# Uninstall tosh daemon and tunnel LaunchAgents

set -euo pipefail

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

echo "=== Uninstalling tosh LaunchAgents ==="

# Stop and unload daemon
echo "Stopping daemon..."
launchctl stop com.tosh.daemon 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/com.tosh.daemon.plist" 2>/dev/null || true

# Stop and unload tunnel
echo "Stopping tunnel..."
launchctl stop com.tosh.tunnel 2>/dev/null || true
launchctl unload "$LAUNCH_AGENTS/com.tosh.tunnel.plist" 2>/dev/null || true

# Remove plist files
echo "Removing plist files..."
rm -f "$LAUNCH_AGENTS/com.tosh.tunnel.plist"
rm -f "$LAUNCH_AGENTS/com.tosh.daemon.plist"

# Remove lock file
rm -f "$HOME/.local/run/tosh-daemon.lock"

echo ""
echo "=== Uninstallation complete ==="
echo ""
echo "Logs preserved in ~/.local/log/"

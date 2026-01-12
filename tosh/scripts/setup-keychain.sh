#!/bin/bash
# Setup Keychain credentials for tosh daemon
# Stores database password securely in macOS Keychain

set -euo pipefail

SERVICE="tosh-comms-db"
ACCOUNT="postgres"

echo "=== tosh Keychain Setup ==="
echo ""
echo "This will store the comms database password in your macOS Keychain."
echo "The daemon will retrieve it securely at runtime."
echo ""

# Check if already exists
if security find-generic-password -s "$SERVICE" -a "$ACCOUNT" >/dev/null 2>&1; then
    echo "Credential already exists for $SERVICE/$ACCOUNT"
    read -p "Overwrite? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    # Delete existing
    security delete-generic-password -s "$SERVICE" -a "$ACCOUNT" 2>/dev/null || true
fi

# Prompt for password
echo "Enter the comms database password:"
read -s DB_PASSWORD

if [[ -z "$DB_PASSWORD" ]]; then
    echo "ERROR: Password cannot be empty"
    exit 1
fi

# Store in Keychain
security add-generic-password \
    -s "$SERVICE" \
    -a "$ACCOUNT" \
    -w "$DB_PASSWORD" \
    -T "" \
    -U

echo ""
echo "=== Credential stored successfully ==="
echo ""
echo "Service: $SERVICE"
echo "Account: $ACCOUNT"
echo ""
echo "To verify:"
echo "  security find-generic-password -s $SERVICE -a $ACCOUNT -w"

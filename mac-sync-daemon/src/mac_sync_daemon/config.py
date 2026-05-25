"""Configuration for mac-sync-daemon."""

import os
from pathlib import Path

# Mac database paths
MESSAGES_DB = Path.home() / "Library/Messages/chat.db"
CALLS_DB = Path.home() / "Library/Application Support/CallHistoryDB/CallHistory.storedata"
CONTACTS_DIR = Path.home() / "Library/Application Support/AddressBook/Sources"

# SSH tunnel config (to reach pg-rhea)
SSH_HOST = os.environ.get("SSH_HOST", "rhea-dev")
SSH_USER = os.environ.get("SSH_USER", "dshanklin")

# Database config (inside the tunnel)
PG_CONTAINER = "owsks0wg4w88s8g84wk00sow"
PG_HOST = os.environ.get("PG_HOST", "10.0.1.5")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DATABASE = os.environ.get("PG_DATABASE", "comms")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi")

# Sync settings
BATCH_SIZE = 1000

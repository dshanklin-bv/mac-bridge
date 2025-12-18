---
project: mac-bridge
type: checklist
phase: 3
component: mac-sync-daemon
date: 2025-12-18
status: not-started
---

# CHECKLIST 03: mac-sync-daemon (Local Sync Service)

## Overview

A simple, AI-free background service that watches macOS databases and syncs changes to PostgreSQL on rhea-dev. **This is NOT an MCP server** - it's a pure data pipeline.

**Key Principle:** Keep it simple. Watch files, detect changes, upload to cloud. No AI, no intelligence, no analysis. That happens server-side.

**Estimated Time:** 6-8 hours
**Dependencies:** Phase 2 (PostgreSQL on rhea-dev)
**Output:** launchd service that runs on boot and syncs data

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    mac-sync-daemon                           │
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │   Watcher    │   │   Watcher    │   │   Watcher    │    │
│  │  Messages    │   │    Calls     │   │  Contacts    │    │
│  │  chat.db     │   │ CallHistory  │   │ AddressBook  │    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │
│         │                  │                  │             │
│         └────────────┬─────┴──────────────────┘             │
│                      │                                       │
│              ┌───────▼───────┐                              │
│              │  Change Queue │                              │
│              │   (SQLite)    │                              │
│              └───────┬───────┘                              │
│                      │                                       │
│              ┌───────▼───────┐                              │
│              │  Sync Engine  │                              │
│              │  - Batching   │                              │
│              │  - Retry      │                              │
│              │  - Dedup      │                              │
│              └───────┬───────┘                              │
│                      │                                       │
└──────────────────────┼───────────────────────────────────────┘
                       │
                       │ PostgreSQL Wire Protocol (SSL)
                       ▼
              ┌────────────────┐
              │   rhea-dev     │
              │   PostgreSQL   │
              │  reeves_data   │
              └────────────────┘
```

---

## Pre-Flight Checks

- [ ] **Check 0.1**: Phase 2 complete (PostgreSQL on rhea-dev)
  ```bash
  psql -h 162.220.24.23 -U mac_bridge -d reeves_data -c 'SELECT 1;'
  ```
  **Expected:** Returns 1 without error

- [ ] **Check 0.2**: Python 3.11+ with watchdog available
  ```bash
  python3 -c "import watchdog; print(watchdog.__version__)"
  ```

- [ ] **Check 0.3**: psycopg2 available
  ```bash
  python3 -c "import psycopg2; print(psycopg2.__version__)"
  ```

---

## Section 1: Project Setup

### 1.1 Create Project Structure

- [ ] **Task 1.1.1**: Create daemon directory
  ```bash
  cd ~/repos/mac-bridge
  mkdir -p mac-sync-daemon/src/mac_sync_daemon
  mkdir -p mac-sync-daemon/tests
  mkdir -p mac-sync-daemon/launchd
  touch mac-sync-daemon/src/mac_sync_daemon/__init__.py
  ```

- [ ] **Task 1.1.2**: Create `pyproject.toml`
  ```toml
  # mac-sync-daemon/pyproject.toml
  [project]
  name = "mac-sync-daemon"
  version = "0.1.0"
  description = "Sync macOS data to PostgreSQL"
  requires-python = ">=3.11"
  dependencies = [
      "watchdog>=3.0.0",
      "psycopg2-binary>=2.9.0",
  ]

  [project.scripts]
  mac-sync-daemon = "mac_sync_daemon.daemon:main"

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"
  ```

- [ ] **Task 1.1.3**: Install dependencies
  ```bash
  cd mac-sync-daemon
  uv venv
  source .venv/bin/activate
  uv pip install -e .
  ```

---

## Section 2: Configuration

### 2.1 Config Module (`config.py`)

- [ ] **Task 2.1.1**: Create configuration module
  ```python
  # src/mac_sync_daemon/config.py
  """Configuration for mac-sync-daemon."""

  import os
  import keyring
  from dataclasses import dataclass
  from typing import Optional

  @dataclass
  class DatabasePaths:
      """Paths to macOS databases."""
      messages: str = os.path.expanduser("~/Library/Messages/chat.db")
      calls: str = os.path.expanduser("~/Library/Application Support/CallHistoryDB/CallHistory.storedata")
      contacts_pattern: str = os.path.expanduser("~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")

  @dataclass
  class PostgresConfig:
      """PostgreSQL connection configuration."""
      host: str = "162.220.24.23"
      port: int = 5432
      database: str = "reeves_data"
      user: str = "mac_bridge"

      @property
      def password(self) -> str:
          """Get password from macOS Keychain."""
          pw = keyring.get_password("mac-sync-daemon", "postgres")
          if not pw:
              raise ValueError("PostgreSQL password not found in Keychain. Run: keyring set mac-sync-daemon postgres")
          return pw

      @property
      def connection_string(self) -> str:
          return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

  @dataclass
  class SyncConfig:
      """Sync behavior configuration."""
      batch_size: int = 100
      sync_interval_seconds: int = 30
      retry_max_attempts: int = 3
      retry_delay_seconds: int = 5

  # Global config instances
  DB_PATHS = DatabasePaths()
  POSTGRES = PostgresConfig()
  SYNC = SyncConfig()
  ```

- [ ] **Task 2.1.2**: Store PostgreSQL password in Keychain
  ```bash
  python3 -c "import keyring; keyring.set_password('mac-sync-daemon', 'postgres', 'YOUR_PASSWORD')"
  ```
  **Record:** Password stored in Keychain? [ ] Yes [ ] No

---

## Section 3: Database Watchers

### 3.1 Base Watcher (`watchers/base.py`)

- [ ] **Task 3.1.1**: Create base watcher class
  ```python
  # src/mac_sync_daemon/watchers/base.py
  """Base class for database file watchers."""

  import os
  import logging
  from abc import ABC, abstractmethod
  from watchdog.observers import Observer
  from watchdog.events import FileSystemEventHandler, FileModifiedEvent

  logger = logging.getLogger(__name__)

  class DatabaseWatcher(ABC, FileSystemEventHandler):
      """Base class for watching SQLite database files."""

      def __init__(self, db_path: str, change_queue):
          self.db_path = db_path
          self.db_dir = os.path.dirname(db_path)
          self.db_name = os.path.basename(db_path)
          self.change_queue = change_queue
          self.observer = None
          self._last_mtime = 0

      def start(self):
          """Start watching the database file."""
          self.observer = Observer()
          self.observer.schedule(self, self.db_dir, recursive=False)
          self.observer.start()
          logger.info(f"Started watching: {self.db_path}")

      def stop(self):
          """Stop watching."""
          if self.observer:
              self.observer.stop()
              self.observer.join()
              logger.info(f"Stopped watching: {self.db_path}")

      def on_modified(self, event):
          """Handle file modification events."""
          if not isinstance(event, FileModifiedEvent):
              return

          # Check if it's our database or its WAL file
          filename = os.path.basename(event.src_path)
          if filename not in [self.db_name, f"{self.db_name}-wal"]:
              return

          # Debounce - check if file actually changed
          try:
              mtime = os.path.getmtime(self.db_path)
              if mtime <= self._last_mtime:
                  return
              self._last_mtime = mtime
          except OSError:
              return

          logger.debug(f"Database modified: {self.db_path}")
          self.on_database_changed()

      @abstractmethod
      def on_database_changed(self):
          """Called when the database file changes. Subclasses implement this."""
          pass

      @abstractmethod
      def get_new_records(self, since_id: int) -> list:
          """Get new records since the given ID. Subclasses implement this."""
          pass
  ```

### 3.2 Messages Watcher (`watchers/messages.py`)

- [ ] **Task 3.2.1**: Create messages watcher
  ```python
  # src/mac_sync_daemon/watchers/messages.py
  """Watcher for macOS Messages database."""

  import sqlite3
  import logging
  from typing import List, Dict, Any
  from .base import DatabaseWatcher

  logger = logging.getLogger(__name__)

  class MessagesWatcher(DatabaseWatcher):
      """Watch Messages chat.db for new messages."""

      def __init__(self, db_path: str, change_queue):
          super().__init__(db_path, change_queue)
          self.last_rowid = self._get_max_rowid()

      def _get_max_rowid(self) -> int:
          """Get the current max ROWID from messages table."""
          try:
              conn = sqlite3.connect(self.db_path)
              cursor = conn.cursor()
              cursor.execute("SELECT MAX(ROWID) FROM message")
              result = cursor.fetchone()[0]
              conn.close()
              return result or 0
          except Exception as e:
              logger.error(f"Error getting max ROWID: {e}")
              return 0

      def on_database_changed(self):
          """Queue new messages for sync."""
          new_records = self.get_new_records(self.last_rowid)
          if new_records:
              for record in new_records:
                  self.change_queue.put(('message', record))
              self.last_rowid = max(r['rowid'] for r in new_records)
              logger.info(f"Queued {len(new_records)} new messages")

      def get_new_records(self, since_id: int) -> List[Dict[str, Any]]:
          """Get messages with ROWID > since_id."""
          try:
              conn = sqlite3.connect(self.db_path)
              conn.row_factory = sqlite3.Row
              cursor = conn.cursor()

              query = """
              SELECT
                  m.ROWID as rowid,
                  m.date,
                  m.text,
                  m.is_from_me,
                  m.handle_id,
                  h.id as handle_identifier,
                  m.cache_roomnames
              FROM message m
              LEFT JOIN handle h ON m.handle_id = h.ROWID
              WHERE m.ROWID > ?
              ORDER BY m.ROWID
              LIMIT 1000
              """

              cursor.execute(query, (since_id,))
              results = [dict(row) for row in cursor.fetchall()]
              conn.close()
              return results
          except Exception as e:
              logger.error(f"Error getting new messages: {e}")
              return []
  ```

### 3.3 Calls Watcher (`watchers/calls.py`)

- [ ] **Task 3.3.1**: Create calls watcher
  ```python
  # src/mac_sync_daemon/watchers/calls.py
  """Watcher for macOS Call History database."""

  import sqlite3
  import logging
  from typing import List, Dict, Any
  from .base import DatabaseWatcher

  logger = logging.getLogger(__name__)

  # Apple epoch offset
  APPLE_EPOCH_OFFSET = 978307200

  class CallsWatcher(DatabaseWatcher):
      """Watch CallHistory.storedata for new calls."""

      def __init__(self, db_path: str, change_queue):
          super().__init__(db_path, change_queue)
          self.last_pk = self._get_max_pk()

      def _get_max_pk(self) -> int:
          """Get the current max Z_PK from ZCALLRECORD table."""
          try:
              conn = sqlite3.connect(self.db_path)
              cursor = conn.cursor()
              cursor.execute("SELECT MAX(Z_PK) FROM ZCALLRECORD")
              result = cursor.fetchone()[0]
              conn.close()
              return result or 0
          except Exception as e:
              logger.error(f"Error getting max Z_PK: {e}")
              return 0

      def on_database_changed(self):
          """Queue new calls for sync."""
          new_records = self.get_new_records(self.last_pk)
          if new_records:
              for record in new_records:
                  self.change_queue.put(('call', record))
              self.last_pk = max(r['pk'] for r in new_records)
              logger.info(f"Queued {len(new_records)} new calls")

      def get_new_records(self, since_pk: int) -> List[Dict[str, Any]]:
          """Get calls with Z_PK > since_pk."""
          try:
              conn = sqlite3.connect(self.db_path)
              conn.row_factory = sqlite3.Row
              cursor = conn.cursor()

              query = """
              SELECT
                  Z_PK as pk,
                  ZDATE as date,
                  ZDURATION as duration,
                  ZADDRESS as phone_number,
                  ZORIGINATED as is_outgoing,
                  ZANSWERED as is_answered,
                  ZCALLTYPE as call_type
              FROM ZCALLRECORD
              WHERE Z_PK > ?
              ORDER BY Z_PK
              LIMIT 1000
              """

              cursor.execute(query, (since_pk,))
              results = [dict(row) for row in cursor.fetchall()]
              conn.close()
              return results
          except Exception as e:
              logger.error(f"Error getting new calls: {e}")
              return []
  ```

### 3.4 Contacts Watcher (`watchers/contacts.py`)

- [ ] **Task 3.4.1**: Create contacts watcher (watches multiple databases)
  ```python
  # src/mac_sync_daemon/watchers/contacts.py
  """Watcher for macOS AddressBook databases."""

  import glob
  import sqlite3
  import logging
  from typing import List, Dict, Any
  from watchdog.observers import Observer
  from watchdog.events import FileSystemEventHandler, FileModifiedEvent

  logger = logging.getLogger(__name__)

  class ContactsWatcher:
      """Watch AddressBook databases for contact changes."""

      def __init__(self, pattern: str, change_queue):
          self.pattern = pattern
          self.change_queue = change_queue
          self.observers = []
          self.db_paths = glob.glob(pattern)
          self.last_modified = {}  # Track per-database state

      def start(self):
          """Start watching all AddressBook databases."""
          for db_path in self.db_paths:
              # TODO: Implement per-database watching
              pass
          logger.info(f"Started watching {len(self.db_paths)} AddressBook databases")

      def stop(self):
          """Stop all watchers."""
          for observer in self.observers:
              observer.stop()
              observer.join()

      def get_all_contacts(self) -> List[Dict[str, Any]]:
          """Get all contacts from all databases (for initial sync)."""
          all_contacts = []
          for db_path in self.db_paths:
              try:
                  conn = sqlite3.connect(db_path)
                  conn.row_factory = sqlite3.Row
                  cursor = conn.cursor()

                  query = """
                  SELECT
                      r.Z_PK as pk,
                      r.ZFIRSTNAME as first_name,
                      r.ZLASTNAME as last_name,
                      r.ZORGANIZATION as organization,
                      p.ZFULLNUMBER as phone,
                      p.ZLABEL as phone_label
                  FROM ZABCDRECORD r
                  LEFT JOIN ZABCDPHONENUMBER p ON r.Z_PK = p.ZOWNER
                  WHERE r.ZFIRSTNAME IS NOT NULL OR r.ZLASTNAME IS NOT NULL
                  """

                  cursor.execute(query)
                  results = [dict(row) for row in cursor.fetchall()]
                  all_contacts.extend(results)
                  conn.close()
              except Exception as e:
                  logger.error(f"Error reading {db_path}: {e}")

          return all_contacts
  ```

---

## Section 4: Sync Engine

### 4.1 Change Queue (`sync/queue.py`)

- [ ] **Task 4.1.1**: Create persistent change queue
  ```python
  # src/mac_sync_daemon/sync/queue.py
  """Persistent queue for changes to sync."""

  import sqlite3
  import json
  import os
  import logging
  from typing import Optional, Tuple, Any
  from threading import Lock

  logger = logging.getLogger(__name__)

  class ChangeQueue:
      """SQLite-backed queue for changes pending sync."""

      def __init__(self, db_path: str = None):
          if db_path is None:
              db_path = os.path.expanduser("~/.mac-sync-daemon/queue.db")
          os.makedirs(os.path.dirname(db_path), exist_ok=True)
          self.db_path = db_path
          self.lock = Lock()
          self._init_db()

      def _init_db(self):
          """Initialize the queue database."""
          conn = sqlite3.connect(self.db_path)
          conn.execute("""
              CREATE TABLE IF NOT EXISTS queue (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_type TEXT NOT NULL,
                  record_data TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  attempts INTEGER DEFAULT 0,
                  last_error TEXT
              )
          """)
          conn.execute("CREATE INDEX IF NOT EXISTS idx_queue_created ON queue(created_at)")
          conn.commit()
          conn.close()

      def put(self, record_type: str, record_data: dict):
          """Add a record to the queue."""
          with self.lock:
              conn = sqlite3.connect(self.db_path)
              conn.execute(
                  "INSERT INTO queue (record_type, record_data) VALUES (?, ?)",
                  (record_type, json.dumps(record_data))
              )
              conn.commit()
              conn.close()

      def get_batch(self, batch_size: int = 100) -> list:
          """Get a batch of records to sync."""
          with self.lock:
              conn = sqlite3.connect(self.db_path)
              conn.row_factory = sqlite3.Row
              cursor = conn.cursor()
              cursor.execute(
                  "SELECT id, record_type, record_data FROM queue ORDER BY id LIMIT ?",
                  (batch_size,)
              )
              results = [(row['id'], row['record_type'], json.loads(row['record_data']))
                         for row in cursor.fetchall()]
              conn.close()
              return results

      def mark_completed(self, ids: list):
          """Remove successfully synced records."""
          if not ids:
              return
          with self.lock:
              conn = sqlite3.connect(self.db_path)
              placeholders = ','.join('?' * len(ids))
              conn.execute(f"DELETE FROM queue WHERE id IN ({placeholders})", ids)
              conn.commit()
              conn.close()

      def mark_failed(self, id: int, error: str):
          """Mark a record as failed and increment attempts."""
          with self.lock:
              conn = sqlite3.connect(self.db_path)
              conn.execute(
                  "UPDATE queue SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                  (error, id)
              )
              conn.commit()
              conn.close()

      def size(self) -> int:
          """Get queue size."""
          conn = sqlite3.connect(self.db_path)
          cursor = conn.cursor()
          cursor.execute("SELECT COUNT(*) FROM queue")
          count = cursor.fetchone()[0]
          conn.close()
          return count
  ```

### 4.2 PostgreSQL Uploader (`sync/uploader.py`)

- [ ] **Task 4.2.1**: Create PostgreSQL uploader
  ```python
  # src/mac_sync_daemon/sync/uploader.py
  """Upload changes to PostgreSQL."""

  import logging
  import psycopg2
  from psycopg2.extras import execute_values
  from datetime import datetime, timezone
  from typing import List, Dict, Any
  from ..config import POSTGRES

  logger = logging.getLogger(__name__)

  # Apple epoch offset
  APPLE_EPOCH_OFFSET = 978307200

  class PostgresUploader:
      """Upload synced data to PostgreSQL."""

      def __init__(self, device_id: str):
          self.device_id = device_id
          self.conn = None

      def connect(self):
          """Establish PostgreSQL connection."""
          self.conn = psycopg2.connect(
              host=POSTGRES.host,
              port=POSTGRES.port,
              database=POSTGRES.database,
              user=POSTGRES.user,
              password=POSTGRES.password,
              sslmode='require'
          )
          logger.info("Connected to PostgreSQL")

      def disconnect(self):
          """Close connection."""
          if self.conn:
              self.conn.close()
              self.conn = None

      def upload_messages(self, messages: List[Dict[str, Any]]) -> int:
          """Upload messages to PostgreSQL. Returns count uploaded."""
          if not messages:
              return 0

          cursor = self.conn.cursor()

          # Convert to PostgreSQL format
          rows = []
          for msg in messages:
              # Convert Apple timestamp to datetime
              ts = msg.get('date', 0)
              if ts:
                  # Apple stores in nanoseconds since 2001
                  if len(str(int(ts))) > 10:
                      ts = ts / 1_000_000_000
                  msg_date = datetime.fromtimestamp(ts + APPLE_EPOCH_OFFSET, tz=timezone.utc)
              else:
                  msg_date = datetime.now(timezone.utc)

              rows.append((
                  self.device_id,
                  str(msg['rowid']),
                  msg.get('handle_identifier', ''),
                  bool(msg.get('is_from_me', False)),
                  msg.get('text', ''),
                  msg_date,
                  msg.get('cache_roomnames', '')
              ))

          # Upsert
          query = """
          INSERT INTO messages (source_device_id, source_message_id, handle_identifier, is_from_me, message_text, message_date, chat_identifier)
          VALUES %s
          ON CONFLICT (source_device_id, source_message_id) DO NOTHING
          """

          execute_values(cursor, query, rows)
          count = cursor.rowcount
          self.conn.commit()
          cursor.close()

          return count

      def upload_calls(self, calls: List[Dict[str, Any]]) -> int:
          """Upload calls to PostgreSQL. Returns count uploaded."""
          if not calls:
              return 0

          cursor = self.conn.cursor()

          rows = []
          for call in calls:
              # Convert Apple timestamp
              ts = call.get('date', 0)
              if ts:
                  call_date = datetime.fromtimestamp(ts + APPLE_EPOCH_OFFSET, tz=timezone.utc)
              else:
                  call_date = datetime.now(timezone.utc)

              phone = call.get('phone_number', '')
              phone_normalized = ''.join(c for c in phone if c.isdigit())

              rows.append((
                  self.device_id,
                  str(call['pk']),
                  phone,
                  phone_normalized,
                  call_date,
                  int(call.get('duration', 0)),
                  bool(call.get('is_outgoing', False)),
                  bool(call.get('is_answered', False)),
                  'voice'  # TODO: map call_type
              ))

          query = """
          INSERT INTO calls (source_device_id, source_call_id, phone_number, phone_normalized, call_date, duration_seconds, is_outgoing, is_answered, call_type)
          VALUES %s
          ON CONFLICT (source_device_id, source_call_id) DO NOTHING
          """

          execute_values(cursor, query, rows)
          count = cursor.rowcount
          self.conn.commit()
          cursor.close()

          return count

      def upload_contacts(self, contacts: List[Dict[str, Any]]) -> int:
          """Upload contacts to PostgreSQL. Returns count uploaded."""
          # TODO: Implement contact sync with phone numbers
          pass
  ```

---

## Section 5: Main Daemon

### 5.1 Daemon Entry Point (`daemon.py`)

- [ ] **Task 5.1.1**: Create main daemon
  ```python
  # src/mac_sync_daemon/daemon.py
  """Main daemon entry point."""

  import signal
  import logging
  import time
  import sys
  from threading import Event

  from .config import DB_PATHS, SYNC
  from .watchers.messages import MessagesWatcher
  from .watchers.calls import CallsWatcher
  from .sync.queue import ChangeQueue
  from .sync.uploader import PostgresUploader

  logging.basicConfig(
      level=logging.INFO,
      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
      handlers=[
          logging.StreamHandler(sys.stdout),
          logging.FileHandler(os.path.expanduser("~/.mac-sync-daemon/daemon.log"))
      ]
  )
  logger = logging.getLogger(__name__)

  class MacDaemon:
      """Main sync daemon."""

      def __init__(self):
          self.shutdown_event = Event()
          self.queue = ChangeQueue()
          self.uploader = None
          self.device_id = None
          self.watchers = []

      def setup(self):
          """Initialize daemon components."""
          # Register device and get ID
          self.uploader = PostgresUploader(device_id=None)  # Will set after registration
          self.uploader.connect()
          self.device_id = self._register_device()
          self.uploader.device_id = self.device_id

          # Create watchers
          self.watchers = [
              MessagesWatcher(DB_PATHS.messages, self.queue),
              CallsWatcher(DB_PATHS.calls, self.queue),
          ]

      def _register_device(self) -> str:
          """Register this device and return its ID."""
          cursor = self.uploader.conn.cursor()
          cursor.execute("""
              INSERT INTO devices (device_name, device_type, last_sync)
              VALUES (%s, %s, NOW())
              ON CONFLICT DO NOTHING
              RETURNING id
          """, (f"{os.uname().nodename}", "mac"))

          result = cursor.fetchone()
          if result:
              device_id = str(result[0])
          else:
              # Already exists, get ID
              cursor.execute("SELECT id FROM devices WHERE device_name = %s", (os.uname().nodename,))
              device_id = str(cursor.fetchone()[0])

          self.uploader.conn.commit()
          cursor.close()
          logger.info(f"Device registered with ID: {device_id}")
          return device_id

      def start(self):
          """Start all watchers."""
          for watcher in self.watchers:
              watcher.start()
          logger.info("All watchers started")

      def stop(self):
          """Stop all watchers."""
          for watcher in self.watchers:
              watcher.stop()
          if self.uploader:
              self.uploader.disconnect()
          logger.info("Daemon stopped")

      def sync_loop(self):
          """Main sync loop."""
          while not self.shutdown_event.is_set():
              try:
                  # Get batch from queue
                  batch = self.queue.get_batch(SYNC.batch_size)

                  if batch:
                      # Group by type
                      messages = [(id, data) for id, type_, data in batch if type_ == 'message']
                      calls = [(id, data) for id, type_, data in batch if type_ == 'call']

                      # Upload
                      if messages:
                          msg_data = [data for _, data in messages]
                          count = self.uploader.upload_messages(msg_data)
                          self.queue.mark_completed([id for id, _ in messages])
                          logger.info(f"Synced {count} messages")

                      if calls:
                          call_data = [data for _, data in calls]
                          count = self.uploader.upload_calls(call_data)
                          self.queue.mark_completed([id for id, _ in calls])
                          logger.info(f"Synced {count} calls")

                  # Sleep before next sync
                  self.shutdown_event.wait(SYNC.sync_interval_seconds)

              except Exception as e:
                  logger.error(f"Sync error: {e}")
                  time.sleep(SYNC.retry_delay_seconds)

      def run(self):
          """Run the daemon."""
          self.setup()
          self.start()
          self.sync_loop()

      def shutdown(self, signum, frame):
          """Handle shutdown signal."""
          logger.info("Shutdown signal received")
          self.shutdown_event.set()
          self.stop()

  def main():
      """Entry point."""
      daemon = MacDaemon()

      # Setup signal handlers
      signal.signal(signal.SIGINT, daemon.shutdown)
      signal.signal(signal.SIGTERM, daemon.shutdown)

      logger.info("Starting mac-sync-daemon...")
      daemon.run()

  if __name__ == "__main__":
      main()
  ```

---

## Section 6: launchd Service

### 6.1 Create launchd plist

- [ ] **Task 6.1.1**: Create launchd plist file
  ```xml
  <!-- launchd/com.dshanklin.mac-sync-daemon.plist -->
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0">
  <dict>
      <key>Label</key>
      <string>com.dshanklin.mac-sync-daemon</string>

      <key>ProgramArguments</key>
      <array>
          <string>/usr/local/bin/python3</string>
          <string>-m</string>
          <string>mac_sync_daemon.daemon</string>
      </array>

      <key>WorkingDirectory</key>
      <string>/Users/dshanklinbv/repos/mac-bridge/mac-sync-daemon</string>

      <key>EnvironmentVariables</key>
      <dict>
          <key>PATH</key>
          <string>/usr/local/bin:/usr/bin:/bin</string>
          <key>PYTHONPATH</key>
          <string>/Users/dshanklinbv/repos/mac-bridge/mac-sync-daemon/src</string>
      </dict>

      <key>RunAtLoad</key>
      <true/>

      <key>KeepAlive</key>
      <true/>

      <key>StandardOutPath</key>
      <string>/Users/dshanklinbv/.mac-sync-daemon/stdout.log</string>

      <key>StandardErrorPath</key>
      <string>/Users/dshanklinbv/.mac-sync-daemon/stderr.log</string>
  </dict>
  </plist>
  ```

### 6.2 Install and Start Service

- [ ] **Task 6.2.1**: Copy plist to LaunchAgents
  ```bash
  cp launchd/com.dshanklin.mac-sync-daemon.plist ~/Library/LaunchAgents/
  ```

- [ ] **Task 6.2.2**: Load the service
  ```bash
  launchctl load ~/Library/LaunchAgents/com.dshanklin.mac-sync-daemon.plist
  ```

- [ ] **Task 6.2.3**: Verify service is running
  ```bash
  launchctl list | grep mac-sync-daemon
  ```
  **Record:** Service running? [ ] Yes [ ] No

---

## Section 7: Testing

### 7.1 Unit Tests

- [ ] **Test 7.1.1**: Test queue operations
  ```python
  # tests/test_queue.py
  def test_queue_put_and_get():
      q = ChangeQueue("/tmp/test_queue.db")
      q.put("message", {"rowid": 1, "text": "test"})
      batch = q.get_batch(10)
      assert len(batch) == 1
      assert batch[0][1] == "message"
  ```

- [ ] **Test 7.1.2**: Run unit tests
  ```bash
  pytest tests/ -v
  ```

### 7.2 Integration Tests

- [ ] **Test 7.2.1**: Test end-to-end message sync
  1. Send a test iMessage to yourself
  2. Wait 60 seconds
  3. Query PostgreSQL for the message
  ```sql
  SELECT * FROM messages WHERE message_text LIKE '%test%' ORDER BY message_date DESC LIMIT 5;
  ```
  **Record:** Message appeared in PostgreSQL? [ ] Yes [ ] No

- [ ] **Test 7.2.2**: Test end-to-end call sync
  1. Make a brief phone call
  2. Wait 60 seconds
  3. Query PostgreSQL for the call
  ```sql
  SELECT * FROM v_calls_with_contacts ORDER BY call_date DESC LIMIT 5;
  ```
  **Record:** Call appeared in PostgreSQL? [ ] Yes [ ] No

---

## Completion Checklist

- [ ] Daemon starts without errors
- [ ] Watchers detect database changes
- [ ] Queue persists records
- [ ] Uploader connects to PostgreSQL
- [ ] Messages sync within 60 seconds
- [ ] Calls sync within 60 seconds
- [ ] launchd service runs on boot
- [ ] Service restarts after crash
- [ ] Logs are useful for debugging

---

## Recording Section

**Date Started:** _________________
**Date Completed:** _________________

**Device ID in PostgreSQL:** _________________

**Average Sync Latency:** _________ seconds

**Issues Encountered:**
1. _________________
2. _________________

---

*This checklist is part of the Mac Bridge project. See `2025-12-18-mac-bridge-project-master-plan.md` for the full plan.*

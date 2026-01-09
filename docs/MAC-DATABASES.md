# Mac Databases Catalog

**Last Verified:** 2025-12-23
**Machine:** Daniel's MacBook Pro

This document catalogs all macOS databases that can be synced to rhea-dev PostgreSQL.

---

## Summary

| Database | Location | Key Tables | Rows | Size | Priority |
|----------|----------|------------|------|------|----------|
| **Messages** | `~/Library/Messages/chat.db` | message, chat, handle | 57,640 / 764 / 1,098 | 88MB | P0 |
| **Call History** | `~/Library/Application Support/CallHistoryDB/CallHistory.storedata` | ZCALLRECORD, ZHANDLE | 275 / 1,569 | 393KB | P0 |
| **Contacts** | `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb` | ZABCDRECORD | ~4,296 total | varies | P0 |
| **Safari History** | `~/Library/Safari/History.db` | history_items, history_visits | 1,589 / 3,204 | 1.3MB | P2 |

---

## 1. Messages (chat.db)

**Path:** `~/Library/Messages/chat.db`
**Size:** 88 MB
**Access:** Requires Full Disk Access

### Tables

```
message                 - 57,640 rows - Individual messages
chat                    - 764 rows    - Conversations
handle                  - 1,098 rows  - Phone numbers/emails
chat_message_join       - Links chats to messages
chat_handle_join        - Links chats to handles (participants)
attachment              - Media files
message_attachment_join - Links messages to attachments
```

### Key Schema: message

```sql
CREATE TABLE message (
  ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
  guid TEXT UNIQUE NOT NULL,           -- Unique message ID
  text TEXT,                           -- Message content
  handle_id INTEGER,                   -- Who sent/received
  date INTEGER,                        -- Apple timestamp (nanoseconds since 2001)
  date_read INTEGER,
  date_delivered INTEGER,
  is_from_me INTEGER,                  -- 1 = outgoing, 0 = incoming
  is_read INTEGER,
  is_delivered INTEGER,
  is_sent INTEGER,
  service TEXT,                        -- 'iMessage' or 'SMS'
  cache_roomnames TEXT,                -- Group chat identifier
  thread_originator_guid TEXT,         -- Reply thread
  -- ... 70+ more columns
);
```

### Key Schema: handle

```sql
CREATE TABLE handle (
  ROWID INTEGER PRIMARY KEY,
  id TEXT NOT NULL,                    -- Phone number or email
  country TEXT,
  service TEXT NOT NULL,               -- 'iMessage' or 'SMS'
  person_centric_id TEXT,              -- iCloud identity
  UNIQUE (id, service)
);
```

### Key Schema: chat

```sql
CREATE TABLE chat (
  ROWID INTEGER PRIMARY KEY,
  guid TEXT UNIQUE NOT NULL,
  chat_identifier TEXT,                -- Phone/email for 1:1, group ID for groups
  service_name TEXT,
  display_name TEXT,                   -- Group name if set
  -- ...
);
```

### Useful Queries

```sql
-- Recent messages with sender
SELECT m.date, m.text, m.is_from_me, h.id as sender
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
ORDER BY m.date DESC
LIMIT 20;

-- Message count by conversation
SELECT c.chat_identifier, COUNT(*) as msg_count
FROM chat c
JOIN chat_message_join cmj ON c.ROWID = cmj.chat_id
GROUP BY c.ROWID
ORDER BY msg_count DESC;
```

### Sync Strategy

- **Watermark:** Track last synced `ROWID` or `date`
- **Incremental:** `SELECT * FROM message WHERE ROWID > last_synced_rowid`
- **Batch size:** 100-500 messages per sync

---

## 2. Call History (CallHistory.storedata)

**Path:** `~/Library/Application Support/CallHistoryDB/CallHistory.storedata`
**Size:** 393 KB
**Access:** Requires Full Disk Access

### Tables

```
ZCALLRECORD             - 275 rows   - Call records
ZHANDLE                 - 1,569 rows - Phone numbers
ZEMERGENCYMEDIAITEM     - Emergency call media
```

### Key Schema: ZCALLRECORD

```sql
CREATE TABLE ZCALLRECORD (
  Z_PK INTEGER PRIMARY KEY,
  ZDATE TIMESTAMP,                     -- Call date (Apple timestamp)
  ZDURATION FLOAT,                     -- Duration in seconds
  ZADDRESS VARCHAR,                    -- Phone number
  ZNAME VARCHAR,                       -- Contact name (if known)
  ZORIGINATED INTEGER,                 -- 1 = outgoing, 0 = incoming
  ZANSWERED INTEGER,                   -- 1 = answered, 0 = missed/declined
  ZCALLTYPE INTEGER,                   -- Type of call
  ZSERVICE_PROVIDER VARCHAR,           -- Carrier info
  ZUNIQUE_ID VARCHAR,                  -- Unique call ID
  -- ...
);
```

### Sample Data

```
Date (Apple TS)       | Duration  | Address       | Name | Out | Ans
788201389.087242      | 270.15s   | +19196245732  |      | 0   | 1
788154148.855007      | 0.0s      | +18284579942  |      | 0   | 0
788141327.036275      | 8.54s     | +18287192293  |      | 1   | 0
```

### Date Conversion

Apple timestamps are seconds since **January 1, 2001**.

```python
from datetime import datetime, timedelta

def apple_to_datetime(apple_ts):
    """Convert Apple timestamp to Python datetime."""
    apple_epoch = datetime(2001, 1, 1)
    return apple_epoch + timedelta(seconds=apple_ts)
```

### Sync Strategy

- **Watermark:** Track last synced `Z_PK` or `ZDATE`
- **Incremental:** `SELECT * FROM ZCALLRECORD WHERE Z_PK > last_synced_pk`
- **Batch size:** 50 calls per sync (low volume)

---

## 3. Contacts (AddressBook)

**Path:** `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb`
**Note:** Multiple database files for different sync sources (iCloud, local, Exchange, etc.)

### Sources Found

| Source UUID | Records |
|-------------|---------|
| 4B0C659C-EAAB-4B76-9509-E90B50CCAF88 | 2,911 |
| 318B86DE-D909-4A37-B00F-BB3F5A7C088D | 1,266 |
| B293E64D-4550-40B4-A418-F06549860D51 | 116 |
| 8FC78B57-1132-49D2-B71D-E47C75B538BF | 3 |
| **Total (may overlap)** | **~4,296** |

### Key Tables

```
ZABCDRECORD             - Contact records (person/org)
ZABCDPHONENUMBER        - Phone numbers
ZABCDEMAILADDRESS       - Email addresses
ZABCDPOSTALADDRESS      - Mailing addresses
ZABCDSOCIALPROFILE      - Social media
ZABCDNOTE               - Notes
ZABCDCONTACTDATE        - Birthdays, anniversaries
```

### Key Schema: ZABCDRECORD

```sql
-- Core contact record (inferred from table name pattern)
-- Contains: first name, last name, organization, job title, etc.
```

### Key Schema: ZABCDPHONENUMBER

```sql
-- Phone numbers linked to ZABCDRECORD
-- Contains: number, label (mobile, home, work), country code
```

### Sync Strategy

- **Deduplication:** Same contact may exist in multiple sources
- **Canonical:** Use iCloud source as primary
- **Incremental:** Track modification timestamps
- **Batch size:** 100 contacts per sync

---

## 4. Safari History

**Path:** `~/Library/Safari/History.db`
**Size:** 1.3 MB
**Access:** Requires Full Disk Access

### Tables

```
history_items           - 1,589 rows - URLs visited
history_visits          - 3,204 rows - Visit records
history_tags            - Tags/folders
```

### Useful Queries

```sql
-- Recent history with visit count
SELECT hi.url, hi.title, COUNT(hv.id) as visits
FROM history_items hi
JOIN history_visits hv ON hi.id = hv.history_item
GROUP BY hi.id
ORDER BY MAX(hv.visit_time) DESC
LIMIT 20;
```

### Priority

**P2 (Low)** - Nice to have but not critical for Reeves.

---

## Access Requirements

All databases require **Full Disk Access** for the process reading them:

1. **System Preferences > Security & Privacy > Privacy > Full Disk Access**
2. Add: Terminal.app, Python, or the sync daemon binary

### Check Access

```bash
# If you can read this, you have Full Disk Access
sqlite3 ~/Library/Messages/chat.db "SELECT COUNT(*) FROM message;"
```

---

## File Locking (WAL Mode)

macOS SQLite databases use WAL (Write-Ahead Logging) mode. Each database has:
- `*.db` or `*.storedata` - Main database
- `*-shm` - Shared memory file
- `*-wal` - Write-ahead log

### Safe Reading

Always open in **read-only mode** to avoid corruption:

```python
import sqlite3

conn = sqlite3.connect(
    f"file:{db_path}?mode=ro",
    uri=True,
    check_same_thread=False
)
```

### Handling Locked Databases

If the app is actively writing, the database may be locked. Solutions:

1. **Retry with backoff** - Wait and try again
2. **Copy the file** - Not recommended (may be inconsistent)
3. **WAL checkpoint** - Force writes to main file (requires write access)

---

## Sync Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                          Mac                                  │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  chat.db    │  │ CallHistory │  │ AddressBook │          │
│  │  (Messages) │  │  .storedata │  │  .abcddb    │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                  │
│         └────────────────┼────────────────┘                  │
│                          │                                   │
│                   ┌──────▼──────┐                            │
│                   │ mac-sync-   │                            │
│                   │ daemon      │                            │
│                   │             │                            │
│                   │ - Watchers  │                            │
│                   │ - Queues    │                            │
│                   │ - Watermarks│                            │
│                   └──────┬──────┘                            │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │ SSH tunnel / Direct PG
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                     rhea-dev (162.220.24.23)                  │
│                                                               │
│                   ┌─────────────────┐                        │
│                   │ PostgreSQL      │                        │
│                   │ (djs_life)      │                        │
│                   │                 │                        │
│                   │ - messages      │                        │
│                   │ - calls         │                        │
│                   │ - contacts      │                        │
│                   │ - sync_state    │                        │
│                   └─────────────────┘                        │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## IP Reporting (Existing)

The IP reporter already works via SSH:

```bash
# Mac reports IP to rhea-dev
ssh rhea-dev "echo {ip} > ~/.mac-ip"

# Current IP on rhea-dev
cat ~/.mac-ip
# 172.20.5.254
```

Same pattern can be used for data sync:
```bash
# Example: Push last message
ssh rhea-dev "psql -d djs_life -c \"INSERT INTO messages (...) VALUES (...);\""
```

---

## Next Steps

1. [ ] Set up PostgreSQL container on rhea-dev (see RHEA-DEV-STATUS.md)
2. [ ] Create Postgres schema matching these tables
3. [ ] Build sync daemon with watchers
4. [ ] Test incremental sync
5. [ ] Add to launchd for automatic startup

---

*This document is auto-generated from database exploration. Update after major macOS upgrades.*

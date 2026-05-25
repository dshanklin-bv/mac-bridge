# Comms-ETL Build Specification

**Purpose:** Server-side ETL service that transforms bronze layer data into silver and gold layers, plus MCP server for Claude access.

**Location:** `/home/dshanklin/repos-personal/mac-bridge/comms-etl/`

**Pattern:** Follow the Cliff project structure (`/home/dshanklin/repos-meetrhea/cliff-data/`)

---

## Overview

The mac-sync-daemon (client-side) pushes raw data to the bronze layer. This service:

1. **Transforms bronze → silver** (clean, normalize, validate)
2. **Transforms silver → gold** (unify, dedupe, enrich)
3. **Provides MCP tools** for Claude to query the gold layer

```
┌─────────────────────────────────────────────────────────────────┐
│  Mac Client                                                      │
│  mac-sync-daemon ──push──▶ bronze.*                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Rhea Server (this service)                                      │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   bronze    │───▶│   silver    │───▶│    gold     │         │
│  │  (raw data) │    │  (cleaned)  │    │  (unified)  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        │                                       │                 │
│        └──── comms-etl transforms ─────────────┘                │
│                                                                  │
│  ┌─────────────┐                                                │
│  │ MCP Server  │◀── Claude queries gold layer                   │
│  └─────────────┘                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Connection

| Field | Value |
|-------|-------|
| **Container** | `owsks0wg4w88s8g84wk00sow` |
| **Host** | `10.0.1.5` (from Coolify network) |
| **Database** | `comms` |
| **User** | `postgres` |
| **Password** | `TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi` |

```bash
# Connection string
postgresql://postgres:TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi@10.0.1.5:5432/comms
```

---

## Project Structure

```
comms-etl/
├── pyproject.toml           # uv project config
├── README.md
├── BUILD-SPEC.md            # This file
│
├── etl/
│   ├── __init__.py
│   ├── config.py            # Database connection, settings
│   ├── db.py                # Database connection pool
│   │
│   ├── bronze_to_silver/
│   │   ├── __init__.py
│   │   ├── apple_messages.py   # Transform messages, handles, chats
│   │   ├── apple_calls.py      # Transform calls
│   │   └── apple_contacts.py   # Transform contacts
│   │
│   ├── silver_to_gold/
│   │   ├── __init__.py
│   │   ├── contacts.py         # Unify contacts, resolve identifiers
│   │   ├── messages.py         # Unify messages across sources
│   │   ├── calls.py            # Unify calls
│   │   └── threads.py          # Build conversation threads
│   │
│   └── main.py              # CLI entry point
│
├── mcp/
│   ├── __init__.py
│   ├── server.py            # FastMCP server
│   └── tools.py             # MCP tools for Claude
│
└── scripts/
    └── run_etl.sh           # Cron wrapper
```

---

## Bronze Layer (Current State)

The bronze layer is populated by mac-sync-daemon. Current counts (as of 2026-01-10):

| Table | Records | Description |
|-------|---------|-------------|
| `bronze.apple_handles` | 1,259 | Phone numbers and emails (contacts) |
| `bronze.apple_chats` | 796 | Conversation threads |
| `bronze.apple_messages` | 58,385 | Individual messages |
| `bronze.apple_calls` | 275 | Call history |
| `bronze.apple_contacts` | 1,119 | Contact records |
| `bronze.apple_contact_phones` | 1,798 | Phone numbers for contacts |
| `bronze.apple_contact_emails` | 772 | Email addresses for contacts |

### Bronze Schemas

```sql
-- bronze.apple_messages
- id, mac_rowid, guid, text
- handle_id (FK to apple_handles.mac_rowid)
- chat_id (FK to apple_chats.mac_rowid)
- date_apple (BIGINT - nanoseconds since 2001-01-01)
- date_read_apple, date_delivered_apple
- is_from_me, is_read, is_delivered, is_sent
- service ('iMessage' or 'SMS')
- thread_originator_guid, associated_message_guid
- cache_has_attachments

-- bronze.apple_handles
- id, mac_rowid, identifier (phone/email)
- service, country, person_centric_id

-- bronze.apple_chats
- id, mac_rowid, guid, chat_identifier
- service_name, display_name, is_archived

-- bronze.apple_calls
- id, mac_pk, unique_id
- date_apple (FLOAT - seconds since 2001-01-01)
- duration_seconds, address, name
- is_outgoing, is_answered, call_type, service_provider

-- bronze.apple_contacts
- id, mac_rowid, source_uuid
- first_name, last_name, organization, job_title, nickname

-- bronze.apple_contact_phones
- id, contact_id (FK), phone_number, label

-- bronze.apple_contact_emails
- id, contact_id (FK), email, label
```

---

## Transformation Logic

### 1. Bronze → Silver

#### apple_messages.py

```python
def transform_messages():
    """
    Transform bronze.apple_messages → silver.apple_messages

    Transformations:
    1. Convert date_apple (nanoseconds) to TIMESTAMPTZ using sync.apple_ns_to_timestamp()
    2. Resolve handle_id → handle_identifier (phone/email)
    3. Resolve chat_id → chat_guid
    4. Normalize service to lowercase ('imessage', 'sms')
    5. Only process records not yet in silver (by bronze_id)
    """

    sql = """
    INSERT INTO silver.apple_messages (
        bronze_id, guid, text, handle_identifier, chat_guid,
        sent_at, read_at, delivered_at, is_from_me, service,
        thread_guid, has_attachments
    )
    SELECT
        bm.id,
        bm.guid,
        bm.text,
        bh.identifier,
        bc.guid,
        sync.apple_ns_to_timestamp(bm.date_apple),
        sync.apple_ns_to_timestamp(bm.date_read_apple),
        sync.apple_ns_to_timestamp(bm.date_delivered_apple),
        bm.is_from_me,
        LOWER(bm.service),
        bm.thread_originator_guid,
        bm.cache_has_attachments
    FROM bronze.apple_messages bm
    LEFT JOIN bronze.apple_handles bh ON bm.handle_id = bh.mac_rowid
    LEFT JOIN bronze.apple_chats bc ON bm.chat_id = bc.mac_rowid
    WHERE bm.id NOT IN (SELECT bronze_id FROM silver.apple_messages WHERE bronze_id IS NOT NULL)
    ON CONFLICT (bronze_id) DO UPDATE SET
        text = EXCLUDED.text,
        read_at = EXCLUDED.read_at,
        processed_at = NOW()
    """
```

#### apple_calls.py

```python
def transform_calls():
    """
    Transform bronze.apple_calls → silver.apple_calls

    Transformations:
    1. Convert date_apple (seconds since 2001) to TIMESTAMPTZ
    2. Normalize phone number using sync.normalize_phone()
    3. Derive direction: is_outgoing → 'outbound'/'inbound'
    4. Derive status: is_answered → 'answered'/'missed'
    """

    sql = """
    INSERT INTO silver.apple_calls (
        bronze_id, unique_id, phone_number, contact_name,
        called_at, duration_seconds, direction, status
    )
    SELECT
        bc.id,
        bc.unique_id,
        sync.normalize_phone(bc.address),
        bc.name,
        sync.apple_sec_to_timestamp(bc.date_apple),
        bc.duration_seconds,
        CASE WHEN bc.is_outgoing THEN 'outbound' ELSE 'inbound' END,
        CASE WHEN bc.is_answered THEN 'answered' ELSE 'missed' END
    FROM bronze.apple_calls bc
    WHERE bc.id NOT IN (SELECT bronze_id FROM silver.apple_calls WHERE bronze_id IS NOT NULL)
    ON CONFLICT (bronze_id) DO NOTHING
    """
```

#### apple_contacts.py

```python
def transform_contacts():
    """
    Transform bronze.apple_contacts → silver.apple_contacts

    Transformations:
    1. Aggregate contacts from multiple AddressBook sources
    2. Build display_name from first_name + last_name
    3. Collect all phone numbers into array
    4. Collect all emails into array
    5. Deduplicate by matching phone/email across sources
    """

    # This is more complex - need to:
    # 1. Group by person (using phone/email overlap)
    # 2. Merge records from different sources
    # 3. Keep track of source_uuids
```

### 2. Silver → Gold

#### contacts.py

```python
def unify_contacts():
    """
    Transform silver.apple_contacts → gold.contacts + gold.contact_identifiers

    Logic:
    1. Create/update gold.contacts with unified profile
    2. Create gold.contact_identifiers for each phone/email
    3. Handle deduplication (same person, different sources)
    4. Link to existing cliff contacts if emails match
    """
```

#### messages.py

```python
def unify_messages():
    """
    Transform silver.apple_messages → gold.messages

    Logic:
    1. For each silver message, find or create gold.contact
    2. Find or create gold.thread
    3. Insert gold.message with proper source tracking
    4. Set direction based on is_from_me
    """

    sql = """
    INSERT INTO gold.messages (
        thread_id, contact_id, source, source_id, source_table,
        direction, content, sent_at, read_at, delivered_at, is_read
    )
    SELECT
        t.id,
        c.id,
        CASE sm.service
            WHEN 'imessage' THEN 'imessage'::gold.message_source
            WHEN 'sms' THEN 'sms'::gold.message_source
        END,
        sm.guid,
        'silver.apple_messages',
        CASE WHEN sm.is_from_me THEN 'outbound' ELSE 'inbound' END::gold.message_direction,
        sm.text,
        sm.sent_at,
        sm.read_at,
        sm.delivered_at,
        sm.read_at IS NOT NULL
    FROM silver.apple_messages sm
    LEFT JOIN gold.contact_identifiers ci ON ci.identifier_value = sm.handle_identifier
    LEFT JOIN gold.contacts c ON ci.contact_id = c.id
    LEFT JOIN gold.threads t ON t.source_thread_id = sm.chat_guid AND t.source =
        CASE sm.service
            WHEN 'imessage' THEN 'imessage'::gold.message_source
            WHEN 'sms' THEN 'sms'::gold.message_source
        END
    WHERE sm.guid NOT IN (SELECT source_id FROM gold.messages WHERE source IN ('imessage', 'sms'))
    ON CONFLICT (source, source_id) DO UPDATE SET
        content = EXCLUDED.content,
        read_at = EXCLUDED.read_at,
        is_read = EXCLUDED.is_read
    """
```

#### calls.py

```python
def unify_calls():
    """
    Transform silver.apple_calls → gold.calls

    Logic:
    1. Match phone_number to gold.contact_identifiers
    2. Insert with proper source='sms' (phone calls via carrier)
    """
```

#### threads.py

```python
def build_threads():
    """
    Create/update gold.threads from silver data

    Logic:
    1. For each unique chat_guid in silver.apple_messages
    2. Create gold.thread if not exists
    3. Update message_count, first_message_at, last_message_at
    4. Extract participant_ids from messages in thread
    """
```

---

## MCP Server Specification

### Tools

```python
# mcp/tools.py

@mcp.tool()
def comms_messages_list(
    source: str | None = None,      # 'imessage', 'sms', 'email', 'all'
    contact: str | None = None,     # Contact name or identifier
    since: str | None = None,       # ISO datetime or relative ('1d', '1w')
    limit: int = 50
) -> list[dict]:
    """List recent messages, optionally filtered by source/contact/time."""

@mcp.tool()
def comms_messages_search(
    query: str,
    source: str | None = None,
    limit: int = 20
) -> list[dict]:
    """Full-text search across all messages."""

@mcp.tool()
def comms_contacts_lookup(
    identifier: str
) -> dict | None:
    """Look up a contact by phone, email, or name."""

@mcp.tool()
def comms_contacts_list(
    limit: int = 100
) -> list[dict]:
    """List all contacts with their identifiers and stats."""

@mcp.tool()
def comms_calls_list(
    direction: str | None = None,   # 'inbound', 'outbound'
    status: str | None = None,      # 'answered', 'missed'
    since: str | None = None,
    limit: int = 50
) -> list[dict]:
    """List recent calls."""

@mcp.tool()
def comms_thread_messages(
    thread_id: int,
    limit: int = 100
) -> list[dict]:
    """Get all messages in a conversation thread."""

@mcp.tool()
def comms_stats() -> dict:
    """Get overview stats: message counts by source, recent activity, etc."""
```

### Server Configuration

```python
# mcp/server.py
from fastmcp import FastMCP

mcp = FastMCP("comms")

# Database connection
DATABASE_URL = os.environ.get(
    "COMMS_DATABASE_URL",
    "postgresql://postgres:TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi@10.0.1.5:5432/comms"
)
```

### pyproject.toml Entry Points

```toml
[project.scripts]
comms-etl = "etl.main:main"
comms-mcp = "mcp.server:main"
```

---

## CLI Usage

```bash
# Run full ETL pipeline
uv run comms-etl

# Run specific transformations
uv run comms-etl --stage bronze-to-silver
uv run comms-etl --stage silver-to-gold

# Run specific source
uv run comms-etl --source messages
uv run comms-etl --source calls
uv run comms-etl --source contacts

# Show stats
uv run comms-etl --stats

# Run MCP server
uv run comms-mcp
```

---

## Scheduling

Add to crontab on rhea-dev:

```bash
# Run ETL every 5 minutes
*/5 * * * * cd /home/dshanklin/repos-personal/mac-bridge/comms-etl && uv run comms-etl >> /var/log/comms-etl.log 2>&1
```

Or use systemd timer for better reliability.

---

## pyproject.toml

```toml
[project]
name = "comms-etl"
version = "0.1.0"
description = "ETL service for unified messaging (bronze → silver → gold)"
requires-python = ">=3.11"
dependencies = [
    "psycopg2-binary>=2.9",
    "fastmcp>=0.1",
    "click>=8.0",
]

[project.scripts]
comms-etl = "etl.main:main"
comms-mcp = "mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## Testing

```bash
# Verify bronze data exists
docker exec owsks0wg4w88s8g84wk00sow psql -U postgres -d comms -c "
SELECT 'bronze.apple_messages' as table_name, count(*) FROM bronze.apple_messages
UNION ALL SELECT 'bronze.apple_calls', count(*) FROM bronze.apple_calls
UNION ALL SELECT 'bronze.apple_contacts', count(*) FROM bronze.apple_contacts;
"

# After running ETL, verify silver
docker exec owsks0wg4w88s8g84wk00sow psql -U postgres -d comms -c "
SELECT 'silver.apple_messages' as table_name, count(*) FROM silver.apple_messages
UNION ALL SELECT 'silver.apple_calls', count(*) FROM silver.apple_calls
UNION ALL SELECT 'silver.apple_contacts', count(*) FROM silver.apple_contacts;
"

# Verify gold
docker exec owsks0wg4w88s8g84wk00sow psql -U postgres -d comms -c "
SELECT 'gold.contacts' as table_name, count(*) FROM gold.contacts
UNION ALL SELECT 'gold.messages', count(*) FROM gold.messages
UNION ALL SELECT 'gold.calls', count(*) FROM gold.calls
UNION ALL SELECT 'gold.threads', count(*) FROM gold.threads;
"
```

---

## Summary

1. **Create project structure** following Cliff pattern
2. **Implement bronze → silver transforms** for messages, calls, contacts
3. **Implement silver → gold transforms** with contact unification
4. **Build MCP server** with query tools for Claude
5. **Set up cron** for periodic ETL runs

The bronze layer is populated and ready. Build this service to complete the pipeline.

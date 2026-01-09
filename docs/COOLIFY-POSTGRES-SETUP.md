# Unified Messaging Database Setup

**Purpose:** Set up a medallion-architecture PostgreSQL database for all personal messaging data - SMS, iMessage, email, LinkedIn, WhatsApp, and any future sources.

**Coolify URL:** http://162.220.24.23:8000

---

## Architecture Overview

A source-agnostic messaging layer using medallion architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                        GOLD LAYER                                │
│                   (Unified Messaging)                            │
│                                                                  │
│   gold.messages        gold.threads        gold.contacts        │
│   ├─ id                ├─ id               ├─ id                │
│   ├─ thread_id         ├─ subject          ├─ display_name      │
│   ├─ contact_id        ├─ participants[]   ├─ identifiers[]     │
│   ├─ direction         ├─ last_message_at  │   (phone, email)   │
│   ├─ content           ├─ message_count    └─ source_links      │
│   ├─ sent_at           └─ status                                │
│   └─ source                                                      │
│       (email | sms | imessage | linkedin | whatsapp | ...)      │
│                                                                  │
│   gold.calls           gold.attachments                         │
│   ├─ id                ├─ id                                    │
│   ├─ contact_id        ├─ message_id                            │
│   ├─ direction         ├─ filename                              │
│   ├─ duration          ├─ mime_type                             │
│   ├─ answered          └─ storage_path                          │
│   └─ source                                                      │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Transform, Dedupe, Enrich
                              │
┌─────────────────────────────┴───────────────────────────────────┐
│                       SILVER LAYER                               │
│              (Cleaned & validated per source)                    │
│                                                                  │
│   silver.apple_messages     silver.apple_contacts               │
│   silver.apple_calls        silver.gmail_emails                 │
│   silver.gmail_contacts     silver.linkedin_messages            │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Clean timestamps, dedupe, validate
                              │
┌─────────────────────────────┴───────────────────────────────────┐
│                       BRONZE LAYER                               │
│                (Raw data exactly as sync'd)                      │
│                                                                  │
│   bronze.apple_messages     bronze.apple_handles                │
│   bronze.apple_chats        bronze.apple_calls                  │
│   bronze.apple_contacts     bronze.gmail_emails                 │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Sync services push raw data
                              │
┌─────────────────────────────┴───────────────────────────────────┐
│                      SYNC SERVICES                               │
│                                                                  │
│   mac-sync-daemon          cliff-sync                           │
│   (Apple Messages,         (Gmail)                              │
│    Calls, Contacts)                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why Medallion Architecture?

| Layer | Purpose | Example |
|-------|---------|---------|
| **Bronze** | Raw data, exactly as received | Apple timestamps (nanoseconds since 2001) |
| **Silver** | Cleaned, validated, source-specific | Timestamps converted to UTC, nulls handled |
| **Gold** | Unified, source-agnostic | One `messages` table for all sources |

**Benefits:**
- Query "all messages from Sarah" regardless of source
- Deduplicate contacts across platforms
- Track conversation threads across channels
- Add new sources without changing gold layer

---

## Step 1: Create Database in Coolify

### Option A: Use Existing `rhea_apps` Database

If `rhea_apps` already exists (used by cliff), add schemas to it:

1. Connect to existing database
2. Run schema creation SQL below

### Option B: Create Dedicated Database

1. **Login to Coolify:** http://162.220.24.23:8000

2. **Create New Resource:**
   - Click **"+ New"** → **"Database"** → **"PostgreSQL"**

3. **Configure:**

   | Setting | Value |
   |---------|-------|
   | **Name** | `djs-life-db` |
   | **PostgreSQL Version** | `17-alpine` |
   | **Database Name** | `djs_life` |
   | **Username** | `daniel` |
   | **Password** | (generate secure) |
   | **Public Port** | `5433` |
   | **Publicly Accessible** | `Yes` |

4. **Deploy** and wait for healthy status

---

## Step 2: Create Schema

Connect and run the following SQL. This creates all three layers.

```sql
-- ============================================================================
-- UNIFIED MESSAGING SCHEMA
-- Medallion Architecture: Bronze → Silver → Gold
-- Database: djs_life (or rhea_apps)
-- ============================================================================

-- Create schemas for each layer
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS sync;

-- ============================================================================
-- SYNC LAYER - Track sync state for each source
-- ============================================================================

CREATE TABLE IF NOT EXISTS sync.sources (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,           -- 'apple_messages', 'gmail', 'linkedin'
    display_name TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMPTZ,
    last_sync_id BIGINT DEFAULT 0,       -- Watermark (ROWID, history_id, etc.)
    last_sync_count INTEGER DEFAULT 0,
    sync_status TEXT DEFAULT 'pending',  -- pending, syncing, success, error
    sync_error TEXT,
    config JSONB,                        -- Source-specific config
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO sync.sources (name, display_name) VALUES
    ('apple_messages', 'Apple Messages (iMessage/SMS)'),
    ('apple_calls', 'Apple Call History'),
    ('apple_contacts', 'Apple Contacts'),
    ('gmail', 'Gmail'),
    ('linkedin', 'LinkedIn Messages'),
    ('whatsapp', 'WhatsApp')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- BRONZE LAYER - Raw data from each source
-- ============================================================================

-- Apple Messages: handles (contacts)
CREATE TABLE IF NOT EXISTS bronze.apple_handles (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,
    identifier TEXT NOT NULL,            -- Phone number or email
    service TEXT,                        -- 'iMessage' or 'SMS'
    country TEXT,
    person_centric_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Apple Messages: chats (conversations)
CREATE TABLE IF NOT EXISTS bronze.apple_chats (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,
    guid TEXT UNIQUE NOT NULL,
    chat_identifier TEXT,
    service_name TEXT,
    display_name TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- Apple Messages: messages
CREATE TABLE IF NOT EXISTS bronze.apple_messages (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,
    guid TEXT UNIQUE NOT NULL,
    text TEXT,
    handle_id INTEGER,                   -- References apple_handles.mac_rowid
    chat_id INTEGER,                     -- References apple_chats.mac_rowid
    date_apple BIGINT,                   -- Raw Apple timestamp (ns since 2001)
    date_read_apple BIGINT,
    date_delivered_apple BIGINT,
    is_from_me BOOLEAN DEFAULT FALSE,
    is_read BOOLEAN DEFAULT FALSE,
    is_delivered BOOLEAN DEFAULT FALSE,
    is_sent BOOLEAN DEFAULT FALSE,
    service TEXT,
    thread_originator_guid TEXT,
    associated_message_guid TEXT,
    cache_has_attachments BOOLEAN DEFAULT FALSE,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bronze_apple_messages_date ON bronze.apple_messages(date_apple DESC);
CREATE INDEX IF NOT EXISTS idx_bronze_apple_messages_handle ON bronze.apple_messages(handle_id);

-- Apple Messages: chat participants
CREATE TABLE IF NOT EXISTS bronze.apple_chat_participants (
    chat_rowid INTEGER NOT NULL,
    handle_rowid INTEGER NOT NULL,
    PRIMARY KEY (chat_rowid, handle_rowid)
);

-- Apple Calls
CREATE TABLE IF NOT EXISTS bronze.apple_calls (
    id SERIAL PRIMARY KEY,
    mac_pk INTEGER UNIQUE NOT NULL,
    unique_id TEXT UNIQUE,
    date_apple FLOAT,                    -- Apple timestamp (seconds since 2001)
    duration_seconds FLOAT,
    address TEXT,                        -- Phone number
    name TEXT,                           -- Contact name if known
    is_outgoing BOOLEAN DEFAULT FALSE,
    is_answered BOOLEAN DEFAULT FALSE,
    call_type INTEGER,
    service_provider TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bronze_apple_calls_date ON bronze.apple_calls(date_apple DESC);

-- Apple Contacts
CREATE TABLE IF NOT EXISTS bronze.apple_contacts (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER NOT NULL,
    source_uuid TEXT NOT NULL,           -- AddressBook source
    first_name TEXT,
    last_name TEXT,
    organization TEXT,
    job_title TEXT,
    nickname TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mac_rowid, source_uuid)
);

CREATE TABLE IF NOT EXISTS bronze.apple_contact_phones (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES bronze.apple_contacts(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    label TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bronze.apple_contact_emails (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES bronze.apple_contacts(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    label TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- SILVER LAYER - Cleaned and validated per source
-- ============================================================================

-- Apple Messages (cleaned)
CREATE TABLE IF NOT EXISTS silver.apple_messages (
    id SERIAL PRIMARY KEY,
    bronze_id INTEGER UNIQUE REFERENCES bronze.apple_messages(id),
    guid TEXT UNIQUE NOT NULL,
    text TEXT,
    handle_identifier TEXT,              -- Resolved from handle
    chat_guid TEXT,
    sent_at TIMESTAMPTZ,                 -- Converted from Apple timestamp
    read_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    is_from_me BOOLEAN,
    service TEXT,                        -- 'imessage' or 'sms'
    thread_guid TEXT,
    has_attachments BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_silver_apple_messages_sent ON silver.apple_messages(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_silver_apple_messages_handle ON silver.apple_messages(handle_identifier);

-- Apple Calls (cleaned)
CREATE TABLE IF NOT EXISTS silver.apple_calls (
    id SERIAL PRIMARY KEY,
    bronze_id INTEGER UNIQUE REFERENCES bronze.apple_calls(id),
    unique_id TEXT UNIQUE,
    phone_number TEXT,                   -- Normalized E.164 format
    contact_name TEXT,
    called_at TIMESTAMPTZ,               -- Converted from Apple timestamp
    duration_seconds FLOAT,
    direction TEXT,                      -- 'inbound' or 'outbound'
    status TEXT,                         -- 'answered', 'missed', 'declined'
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_silver_apple_calls_date ON silver.apple_calls(called_at DESC);

-- Apple Contacts (cleaned, deduplicated across sources)
CREATE TABLE IF NOT EXISTS silver.apple_contacts (
    id SERIAL PRIMARY KEY,
    display_name TEXT,
    first_name TEXT,
    last_name TEXT,
    organization TEXT,
    phone_numbers TEXT[],                -- Array of all phone numbers
    email_addresses TEXT[],              -- Array of all emails
    source_uuids TEXT[],                 -- Which AddressBook sources
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_silver_apple_contacts_name ON silver.apple_contacts(display_name);
CREATE INDEX IF NOT EXISTS idx_silver_apple_contacts_phones ON silver.apple_contacts USING GIN(phone_numbers);

-- ============================================================================
-- GOLD LAYER - Unified messaging model
-- ============================================================================

-- Message sources enum (extensible)
CREATE TYPE gold.message_source AS ENUM (
    'email',
    'sms',
    'imessage',
    'linkedin',
    'whatsapp',
    'slack',
    'signal',
    'telegram',
    'messenger'
);

CREATE TYPE gold.message_direction AS ENUM ('inbound', 'outbound');
CREATE TYPE gold.call_status AS ENUM ('answered', 'missed', 'declined', 'voicemail');

-- Unified Contacts
CREATE TABLE IF NOT EXISTS gold.contacts (
    id SERIAL PRIMARY KEY,
    display_name TEXT,
    first_name TEXT,
    last_name TEXT,
    organization TEXT,
    notes TEXT,

    -- Importance/relationship
    relationship TEXT,                   -- 'family', 'friend', 'work', 'vendor', etc.
    importance TEXT DEFAULT 'normal',    -- 'critical', 'high', 'normal', 'low'

    -- Stats (updated by triggers/jobs)
    total_messages_received INTEGER DEFAULT 0,
    total_messages_sent INTEGER DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    last_contact_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contact identifiers (phone, email, handle, etc.)
CREATE TABLE IF NOT EXISTS gold.contact_identifiers (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES gold.contacts(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL,       -- 'phone', 'email', 'linkedin', 'whatsapp', etc.
    identifier_value TEXT NOT NULL,      -- The actual phone/email/handle
    is_primary BOOLEAN DEFAULT FALSE,
    verified BOOLEAN DEFAULT FALSE,
    source TEXT,                         -- Which system provided this
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (identifier_type, identifier_value)
);

CREATE INDEX IF NOT EXISTS idx_gold_identifiers_value ON gold.contact_identifiers(identifier_value);
CREATE INDEX IF NOT EXISTS idx_gold_identifiers_contact ON gold.contact_identifiers(contact_id);

-- Unified Threads (conversations)
CREATE TABLE IF NOT EXISTS gold.threads (
    id SERIAL PRIMARY KEY,
    subject TEXT,                        -- For email, or group chat name
    source gold.message_source NOT NULL,
    source_thread_id TEXT,               -- Original thread ID from source

    -- Participants (contact IDs)
    participant_ids INTEGER[],
    participant_display TEXT[],          -- Cached display names

    -- Stats
    message_count INTEGER DEFAULT 0,
    first_message_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    last_sender_id INTEGER,

    -- Status
    status TEXT DEFAULT 'active',        -- 'active', 'archived', 'muted'
    is_group BOOLEAN DEFAULT FALSE,

    -- AI enrichment
    summary TEXT,
    summary_updated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (source, source_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_gold_threads_last ON gold.threads(last_message_at DESC);
CREATE INDEX IF NOT EXISTS idx_gold_threads_source ON gold.threads(source);

-- Unified Messages
CREATE TABLE IF NOT EXISTS gold.messages (
    id SERIAL PRIMARY KEY,
    thread_id INTEGER REFERENCES gold.threads(id),
    contact_id INTEGER REFERENCES gold.contacts(id),

    -- Source tracking
    source gold.message_source NOT NULL,
    source_id TEXT NOT NULL,             -- Original ID from source system
    source_table TEXT,                   -- 'silver.apple_messages', etc.

    -- Content
    direction gold.message_direction NOT NULL,
    content TEXT,
    content_html TEXT,                   -- For rich content (email)
    subject TEXT,                        -- For email

    -- Timestamps
    sent_at TIMESTAMPTZ NOT NULL,
    read_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,

    -- Status
    is_read BOOLEAN DEFAULT FALSE,

    -- Attachments count (details in gold.attachments)
    attachment_count INTEGER DEFAULT 0,

    -- AI enrichment
    sentiment TEXT,                      -- 'positive', 'negative', 'neutral'
    action_required BOOLEAN DEFAULT FALSE,
    action_description TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_gold_messages_sent ON gold.messages(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_gold_messages_thread ON gold.messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_gold_messages_contact ON gold.messages(contact_id);
CREATE INDEX IF NOT EXISTS idx_gold_messages_source ON gold.messages(source);
CREATE INDEX IF NOT EXISTS idx_gold_messages_unread ON gold.messages(is_read) WHERE is_read = FALSE;

-- Full-text search on messages
ALTER TABLE gold.messages ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(content, '')), 'B')
    ) STORED;
CREATE INDEX IF NOT EXISTS idx_gold_messages_fts ON gold.messages USING GIN(search_vector);

-- Unified Calls
CREATE TABLE IF NOT EXISTS gold.calls (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES gold.contacts(id),

    -- Source tracking
    source gold.message_source NOT NULL, -- Usually 'phone' but could be 'whatsapp', etc.
    source_id TEXT NOT NULL,

    -- Call details
    direction gold.message_direction NOT NULL,
    status gold.call_status NOT NULL,
    called_at TIMESTAMPTZ NOT NULL,
    duration_seconds FLOAT,

    -- For video calls
    is_video BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_gold_calls_date ON gold.calls(called_at DESC);
CREATE INDEX IF NOT EXISTS idx_gold_calls_contact ON gold.calls(contact_id);

-- Attachments
CREATE TABLE IF NOT EXISTS gold.attachments (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES gold.messages(id) ON DELETE CASCADE,

    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,

    -- Storage location
    storage_path TEXT,
    storage_url TEXT,

    -- For documents: extracted text
    extracted_text TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gold_attachments_message ON gold.attachments(message_id);

-- ============================================================================
-- VIEWS - AI-friendly queries
-- ============================================================================

-- Recent messages across all sources
CREATE OR REPLACE VIEW gold.v_recent_messages AS
SELECT
    m.id,
    m.source,
    m.direction,
    m.content,
    m.subject,
    m.sent_at,
    m.is_read,
    c.display_name as contact_name,
    t.subject as thread_subject,
    t.is_group
FROM gold.messages m
LEFT JOIN gold.contacts c ON m.contact_id = c.id
LEFT JOIN gold.threads t ON m.thread_id = t.id
ORDER BY m.sent_at DESC;

-- Unread messages
CREATE OR REPLACE VIEW gold.v_unread AS
SELECT * FROM gold.v_recent_messages
WHERE is_read = FALSE AND direction = 'inbound';

-- Recent calls
CREATE OR REPLACE VIEW gold.v_recent_calls AS
SELECT
    c.id,
    c.source,
    c.direction,
    c.status,
    c.called_at,
    c.duration_seconds,
    ROUND(c.duration_seconds / 60.0, 1) as duration_minutes,
    ct.display_name as contact_name
FROM gold.calls c
LEFT JOIN gold.contacts ct ON c.contact_id = ct.id
ORDER BY c.called_at DESC;

-- Contact lookup with all identifiers
CREATE OR REPLACE VIEW gold.v_contacts AS
SELECT
    c.id,
    c.display_name,
    c.first_name,
    c.last_name,
    c.organization,
    c.relationship,
    c.importance,
    c.total_messages_received,
    c.total_messages_sent,
    c.last_message_at,
    ARRAY_AGG(DISTINCT ci.identifier_value) FILTER (WHERE ci.identifier_type = 'phone') as phones,
    ARRAY_AGG(DISTINCT ci.identifier_value) FILTER (WHERE ci.identifier_type = 'email') as emails
FROM gold.contacts c
LEFT JOIN gold.contact_identifiers ci ON c.id = ci.contact_id
GROUP BY c.id;

-- Thread overview
CREATE OR REPLACE VIEW gold.v_threads AS
SELECT
    t.id,
    t.source,
    t.subject,
    t.is_group,
    t.status,
    t.message_count,
    t.first_message_at,
    t.last_message_at,
    t.participant_display,
    t.summary
FROM gold.threads t
ORDER BY t.last_message_at DESC;

-- ============================================================================
-- FUNCTIONS - Data transformation
-- ============================================================================

-- Convert Apple timestamp (nanoseconds since 2001-01-01) to TIMESTAMPTZ
CREATE OR REPLACE FUNCTION sync.apple_ns_to_timestamp(apple_ns BIGINT)
RETURNS TIMESTAMPTZ AS $$
BEGIN
    IF apple_ns IS NULL OR apple_ns = 0 THEN
        RETURN NULL;
    END IF;
    -- Apple epoch is 2001-01-01, timestamps are in nanoseconds
    RETURN TIMESTAMP '2001-01-01 00:00:00 UTC' + (apple_ns / 1000000000.0) * INTERVAL '1 second';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Convert Apple timestamp (seconds since 2001-01-01) to TIMESTAMPTZ
CREATE OR REPLACE FUNCTION sync.apple_sec_to_timestamp(apple_sec FLOAT)
RETURNS TIMESTAMPTZ AS $$
BEGIN
    IF apple_sec IS NULL OR apple_sec = 0 THEN
        RETURN NULL;
    END IF;
    RETURN TIMESTAMP '2001-01-01 00:00:00 UTC' + apple_sec * INTERVAL '1 second';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Normalize phone number (basic - extend as needed)
CREATE OR REPLACE FUNCTION sync.normalize_phone(phone TEXT)
RETURNS TEXT AS $$
BEGIN
    IF phone IS NULL THEN
        RETURN NULL;
    END IF;
    -- Remove non-digits except leading +
    RETURN regexp_replace(phone, '[^0-9+]', '', 'g');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- Done!
-- ============================================================================
```

---

## Step 3: Store Credentials

On the Mac, store the database password in Keychain:

```bash
security add-generic-password \
    -a "djs-life-sync" \
    -s "djs-life-postgres" \
    -w "YOUR_PASSWORD_HERE" \
    -U
```

Retrieve in Python:

```python
import subprocess

def get_db_password():
    result = subprocess.run(
        ["security", "find-generic-password",
         "-a", "djs-life-sync",
         "-s", "djs-life-postgres",
         "-w"],
        capture_output=True, text=True
    )
    return result.stdout.strip()
```

---

## Step 4: Verify Setup

```bash
# From Mac
psql -h 162.220.24.23 -p 5433 -U daniel -d djs_life -c "
    SELECT schema_name FROM information_schema.schemata
    WHERE schema_name IN ('bronze', 'silver', 'gold', 'sync');
"

# Should return: bronze, silver, gold, sync

# Check sources
psql -h 162.220.24.23 -p 5433 -U daniel -d djs_life -c "
    SELECT name, display_name, enabled FROM sync.sources;
"
```

---

## Connection Details

| Field | Value |
|-------|-------|
| **Host** | `162.220.24.23` |
| **Port** | `5433` |
| **Database** | `djs_life` |
| **User** | `daniel` |
| **Schemas** | `bronze`, `silver`, `gold`, `sync` |

**Connection String:**
```
postgresql://daniel:PASSWORD@162.220.24.23:5433/djs_life
```

---

## Sync Flow

For each source (Apple Messages, Gmail, etc.):

```
1. EXTRACT: Read from source (chat.db, Gmail API)
       ↓
2. LOAD to BRONZE: Insert raw data as-is
       ↓
3. TRANSFORM to SILVER: Clean, validate, normalize timestamps
       ↓
4. MERGE to GOLD: Dedupe contacts, link threads, unify format
       ↓
5. UPDATE sync.sources: Record watermark for next sync
```

---

## Example Queries (Gold Layer)

```sql
-- What messages did I get today?
SELECT source, direction, contact_name, content, sent_at
FROM gold.v_recent_messages
WHERE sent_at > NOW() - INTERVAL '1 day'
  AND direction = 'inbound';

-- Who have I been talking to most?
SELECT contact_name, COUNT(*) as message_count
FROM gold.v_recent_messages
GROUP BY contact_name
ORDER BY message_count DESC
LIMIT 10;

-- Search all messages
SELECT * FROM gold.messages
WHERE search_vector @@ to_tsquery('english', 'meeting & tomorrow');

-- Missed calls this week
SELECT * FROM gold.v_recent_calls
WHERE status = 'missed'
  AND called_at > NOW() - INTERVAL '7 days';
```

---

## Relationship to Cliff (Email)

Cliff already syncs Gmail. To integrate:

1. Cliff continues to manage `cliff.*` schema
2. Add transformation job: `cliff.emails` → `gold.messages`
3. Or: Modify cliff to write directly to bronze/silver/gold layers

The gold layer becomes the **single source of truth** for all messaging.

---

## Next Steps

1. [ ] Provision database in Coolify
2. [ ] Run schema SQL
3. [ ] Store credentials in Keychain
4. [ ] Build mac-sync-daemon (bronze layer sync)
5. [ ] Build transformation jobs (bronze → silver → gold)
6. [ ] Integrate cliff email data
7. [ ] Build MCP server for Claude access

---

*Document created: 2025-01-08*
*Architecture: Medallion (Bronze/Silver/Gold)*
*For: Unified personal messaging system*

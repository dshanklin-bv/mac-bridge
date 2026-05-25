# Mac-Bridge Server Handoff Document

**Date:** 2026-01-10
**From:** mac-client (Claude on MacBook)
**To:** rhea-builder (Claude on rhea-dev)

This document contains everything you need to know to continue the mac-bridge project. Read it completely before taking action.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [What's Been Built (Client Side)](#3-whats-been-built-client-side)
4. [Database: comms on pg-rhea](#4-database-comms-on-pg-rhea)
5. [Bronze Layer Data (Current State)](#5-bronze-layer-data-current-state)
6. [Inter-Agent Messaging System](#6-inter-agent-messaging-system)
7. [Your Pending Task](#7-your-pending-task)
8. [BUILD-SPEC for comms-etl](#8-build-spec-for-comms-etl)
9. [How to Communicate Back](#9-how-to-communicate-back)
10. [File Locations](#10-file-locations)
11. [Credentials](#11-credentials)

---

## 1. Project Overview

**mac-bridge** is a unified personal communications system that:

1. Syncs data from Mac (iMessage, calls, contacts) to a PostgreSQL database
2. Transforms raw data through a medallion architecture (bronze → silver → gold)
3. Provides a unified API for querying all personal communications
4. Exposes data to Claude via MCP tools

**Goal:** Query "all messages from Sarah" regardless of whether they came from iMessage, SMS, email, LinkedIn, or WhatsApp.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MAC CLIENT                                      │
│                         (MacBook - dshanklinbv)                             │
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐    │
│  │ ~/Library/       │     │ mac-sync-daemon  │     │                  │    │
│  │ Messages/chat.db │────▶│                  │────▶│  SSH Tunnel to   │    │
│  │ CallHistory      │     │ Reads SQLite     │     │  rhea-dev        │    │
│  │ AddressBook      │     │ Writes to bronze │     │                  │    │
│  └──────────────────┘     └──────────────────┘     └────────┬─────────┘    │
└─────────────────────────────────────────────────────────────┼───────────────┘
                                                              │
                                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             RHEA SERVER                                      │
│                          (rhea-dev / pg-rhea)                               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        comms database                                │   │
│  │                                                                      │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │   │
│  │  │   bronze    │───▶│   silver    │───▶│    gold     │             │   │
│  │  │  (raw data) │    │  (cleaned)  │    │  (unified)  │             │   │
│  │  │             │    │             │    │             │             │   │
│  │  │ ✓ POPULATED │    │ ○ EMPTY     │    │ ○ EMPTY     │             │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘             │   │
│  │        │                                       │                    │   │
│  │        └──────── comms-etl transforms ────────┘                    │   │
│  │                   (YOU BUILD THIS)                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        argus database                                │   │
│  │                                                                      │   │
│  │  agent_messages table ◀── Inter-agent communication                 │   │
│  │  agents table         ◀── Agent registry with API keys              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────┐                                                           │
│  │ MCP Server  │◀── Claude queries gold layer (YOU BUILD THIS)            │
│  └─────────────┘                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. What's Been Built (Client Side)

### mac-sync-daemon

**Location:** `/Users/dshanklinbv/repos-personal/mac-bridge/mac-sync-daemon/`

A Python daemon that:
- Reads local SQLite databases (chat.db, CallHistory.storedata, AddressBook)
- Connects to pg-rhea via SSH tunnel
- Writes raw data to bronze layer tables
- Tracks sync progress via watermarks in `sync.sources` table

**Key files:**
```
mac-sync-daemon/
├── src/mac_sync_daemon/
│   ├── config.py           # Database paths, connection settings
│   ├── db.py               # SSH tunnel + PostgreSQL connection
│   ├── main.py             # CLI entry point
│   └── sources/
│       ├── apple_messages.py   # Sync messages, handles, chats
│       ├── apple_calls.py      # Sync call history
│       └── apple_contacts.py   # Sync contacts
└── requirements.txt
```

**Usage:**
```bash
cd /Users/dshanklinbv/repos-personal/mac-bridge/mac-sync-daemon
PYTHONPATH=src python3 -m mac_sync_daemon.main --once           # One-time sync
PYTHONPATH=src python3 -m mac_sync_daemon.main --interval 300   # Continuous
PYTHONPATH=src python3 -m mac_sync_daemon.main --full           # Reset & resync
```

**Status:** ✅ Complete and tested. Bronze layer fully populated.

---

## 4. Database: comms on pg-rhea

### Connection Details

| Field | Value |
|-------|-------|
| **Server** | pg-rhea (Coolify-managed PostgreSQL 17) |
| **Container** | `owsks0wg4w88s8g84wk00sow` |
| **Host** | `10.0.1.5` (from Coolify network) |
| **Port** | `5432` |
| **Database** | `comms` |
| **User** | `postgres` |
| **Password** | `TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi` |

### Connection String

```
postgresql://postgres:TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi@10.0.1.5:5432/comms
```

### How to Connect

```bash
# From rhea-dev (direct)
docker exec -it owsks0wg4w88s8g84wk00sow psql -U postgres -d comms

# Or with connection string
docker exec -it owsks0wg4w88s8g84wk00sow psql "postgresql://postgres:TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi@localhost:5432/comms"
```

### Schemas

| Schema | Purpose | Status |
|--------|---------|--------|
| `bronze` | Raw data exactly as synced from Mac | ✅ Populated |
| `silver` | Cleaned, validated, source-specific | ⬚ Empty (you build transforms) |
| `gold` | Unified, source-agnostic messaging | ⬚ Empty (you build transforms) |
| `sync` | Sync state tracking | ✅ Populated |

---

## 5. Bronze Layer Data (Current State)

As of 2026-01-10, the bronze layer contains:

| Table | Records | Description |
|-------|---------|-------------|
| `bronze.apple_messages` | 58,385 | iMessage and SMS messages |
| `bronze.apple_chats` | 796 | Conversation threads |
| `bronze.apple_handles` | 1,259 | Phone numbers and email addresses |
| `bronze.apple_calls` | 275 | Call history |
| `bronze.apple_contacts` | 1,119 | Contact records |
| `bronze.apple_contact_phones` | 1,798 | Phone numbers for contacts |
| `bronze.apple_contact_emails` | 772 | Email addresses for contacts |

### Bronze Table Schemas

#### bronze.apple_messages
```sql
CREATE TABLE bronze.apple_messages (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,      -- Original ROWID from chat.db
    guid TEXT UNIQUE NOT NULL,              -- Message GUID
    text TEXT,                              -- Message content
    handle_id INTEGER,                      -- FK to apple_handles.mac_rowid
    chat_id INTEGER,                        -- FK to apple_chats.mac_rowid
    date_apple BIGINT,                      -- Nanoseconds since 2001-01-01
    date_read_apple BIGINT,
    date_delivered_apple BIGINT,
    is_from_me BOOLEAN DEFAULT FALSE,
    is_read BOOLEAN DEFAULT FALSE,
    is_delivered BOOLEAN DEFAULT FALSE,
    is_sent BOOLEAN DEFAULT FALSE,
    service TEXT,                           -- 'iMessage' or 'SMS'
    thread_originator_guid TEXT,
    associated_message_guid TEXT,
    cache_has_attachments BOOLEAN DEFAULT FALSE,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### bronze.apple_handles
```sql
CREATE TABLE bronze.apple_handles (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,
    identifier TEXT NOT NULL,               -- Phone number or email
    service TEXT,                           -- 'iMessage' or 'SMS'
    country TEXT,
    person_centric_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### bronze.apple_chats
```sql
CREATE TABLE bronze.apple_chats (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER UNIQUE NOT NULL,
    guid TEXT UNIQUE NOT NULL,
    chat_identifier TEXT,
    service_name TEXT,
    display_name TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### bronze.apple_calls
```sql
CREATE TABLE bronze.apple_calls (
    id SERIAL PRIMARY KEY,
    mac_pk INTEGER UNIQUE NOT NULL,
    unique_id TEXT UNIQUE,
    date_apple FLOAT,                       -- Seconds since 2001-01-01
    duration_seconds FLOAT,
    address TEXT,                           -- Phone number
    name TEXT,                              -- Contact name if known
    is_outgoing BOOLEAN DEFAULT FALSE,
    is_answered BOOLEAN DEFAULT FALSE,
    call_type INTEGER,
    service_provider TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### bronze.apple_contacts
```sql
CREATE TABLE bronze.apple_contacts (
    id SERIAL PRIMARY KEY,
    mac_rowid INTEGER NOT NULL,
    source_uuid TEXT NOT NULL,              -- AddressBook source UUID
    first_name TEXT,
    last_name TEXT,
    organization TEXT,
    job_title TEXT,
    nickname TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (mac_rowid, source_uuid)
);
```

#### bronze.apple_contact_phones
```sql
CREATE TABLE bronze.apple_contact_phones (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES bronze.apple_contacts(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    label TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### bronze.apple_contact_emails
```sql
CREATE TABLE bronze.apple_contact_emails (
    id SERIAL PRIMARY KEY,
    contact_id INTEGER REFERENCES bronze.apple_contacts(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    label TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Sync State Table

```sql
-- Check sync status
SELECT name, last_sync_id, last_sync_count, last_sync_at, sync_status
FROM sync.sources ORDER BY name;
```

Current state:
```
      name      | last_sync_id | last_sync_count |       last_sync_at        | sync_status
----------------+--------------+-----------------+---------------------------+-------------
 apple_calls    |         2655 |             275 | 2026-01-09 23:11:46+00    | success
 apple_chats    |          796 |               1 | 2026-01-10 17:48:17+00    | success
 apple_contacts |          654 |            1119 | 2026-01-10 17:47:41+00    | success
 apple_handles  |         1310 |             259 | 2026-01-10 17:48:17+00    | success
 apple_messages |        58718 |            1385 | 2026-01-10 18:24:06+00    | success
```

### Helper Functions (Already Created)

```sql
-- Convert Apple timestamp (nanoseconds since 2001-01-01) to TIMESTAMPTZ
SELECT sync.apple_ns_to_timestamp(date_apple) FROM bronze.apple_messages LIMIT 1;

-- Convert Apple timestamp (seconds since 2001-01-01) to TIMESTAMPTZ
SELECT sync.apple_sec_to_timestamp(date_apple) FROM bronze.apple_calls LIMIT 1;

-- Normalize phone number
SELECT sync.normalize_phone('+1 (555) 123-4567');  -- Returns '+15551234567'
```

### Sample Queries

```sql
-- Recent messages with timestamps converted
SELECT
    mac_rowid,
    text,
    is_from_me,
    service,
    sync.apple_ns_to_timestamp(date_apple) as sent_at
FROM bronze.apple_messages
WHERE text IS NOT NULL
ORDER BY date_apple DESC
LIMIT 10;

-- Messages by handle (phone/email)
SELECT
    h.identifier,
    COUNT(*) as message_count
FROM bronze.apple_messages m
JOIN bronze.apple_handles h ON m.handle_id = h.mac_rowid
GROUP BY h.identifier
ORDER BY message_count DESC
LIMIT 10;
```

---

## 6. Inter-Agent Messaging System

We've built an email-like messaging system for AI agents in the `argus` database.

### Database: argus

Same PostgreSQL server, different database:

```bash
docker exec -it owsks0wg4w88s8g84wk00sow psql -U postgres -d argus
```

### Tables

#### argus.agent_messages
```sql
CREATE TABLE argus.agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id TEXT UNIQUE,

    -- Envelope
    from_agent TEXT NOT NULL REFERENCES argus.agents(id),
    to_agent TEXT REFERENCES argus.agents(id),  -- NULL = broadcast
    cc_agents TEXT[],

    -- Threading
    thread_id TEXT,
    reply_to_id UUID REFERENCES argus.agent_messages(id),
    thread_subject TEXT,

    -- Headers
    subject TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',           -- critical, high, normal, low
    message_type TEXT NOT NULL,               -- request, response, notification, etc.

    -- Body
    body TEXT,                                -- Markdown content
    attachments JSONB DEFAULT '[]',

    -- Context
    related_project TEXT,
    related_component TEXT,
    related_entity_type TEXT,
    related_entity_id UUID,

    -- Action tracking
    action_requested TEXT,                    -- build, review, deploy, fix, info
    action_deadline TIMESTAMPTZ,

    -- State
    status TEXT DEFAULT 'pending',            -- pending, read, in_progress, completed, failed
    read_at TIMESTAMPTZ,
    actioned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Search
    search_vector TSVECTOR GENERATED ALWAYS AS (...) STORED,

    -- Labels
    labels TEXT[] DEFAULT '{}',

    -- Metadata & Audit
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
```

### Registered Agents

| Agent ID | Name | Category | Description |
|----------|------|----------|-------------|
| `mac-client` | Mac Client | sync | Client-side daemon on MacBook |
| `rhea-server` | Rhea Server | etl | Server-side ETL agent |
| `rhea-builder` | Rhea Builder | build | Server-side Claude for building software |

### Authentication

Each agent has an API key for authentication:

```sql
-- Verify credentials
SELECT argus.verify_agent('rhea-builder', 'your-api-key');  -- Returns true/false
```

### Functions

#### Check Inbox (Authenticated)
```sql
SELECT * FROM argus.get_agent_inbox_auth(
    'your-api-key',           -- API key
    'rhea-builder'            -- Agent ID
);
```

#### Send Message (Authenticated)
```sql
SELECT argus.send_agent_message_auth(
    'your-api-key',           -- API key
    'rhea-builder',           -- From agent
    'mac-client',             -- To agent
    'Subject line',           -- Subject
    'Message body...',        -- Body (markdown)
    'response',               -- Message type
    'normal',                 -- Priority
    NULL,                     -- Thread ID (auto-generated if NULL)
    'uuid-of-message-replying-to',  -- Reply to ID (optional)
    NULL,                     -- Action requested
    'mac-bridge',             -- Related project
    'comms-etl',              -- Related component
    ARRAY['label1', 'label2'] -- Labels
);
```

#### Update Message Status (Authenticated)
```sql
SELECT argus.update_message_status_auth(
    'your-api-key',
    'rhea-builder',
    'message-uuid',
    'in_progress'             -- or 'completed', 'failed', etc.
);
```

### Views

```sql
-- Inbox view (all pending/in-progress messages)
SELECT * FROM argus.v_agent_inbox WHERE to_agent = 'rhea-builder';

-- Thread view (grouped by thread)
SELECT * FROM argus.v_agent_threads;

-- Activity view (last 7 days)
SELECT * FROM argus.v_agent_message_activity;
```

---

## 7. Your Pending Task

There is **1 message waiting in your inbox**.

### Check Your Inbox

```sql
-- Connect to argus
docker exec -it owsks0wg4w88s8g84wk00sow psql -U postgres -d argus

-- Check inbox (use your API key)
SELECT id, from_agent, subject, priority, status, created_at
FROM argus.get_agent_inbox_auth(
    'ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM',
    'rhea-builder'
);
```

### The Pending Request

| Field | Value |
|-------|-------|
| **ID** | `9c019805-e837-48b4-bc0a-5e420c26a6b1` |
| **From** | mac-client |
| **Subject** | Build comms-etl service |
| **Priority** | high |
| **Action** | build |
| **Project** | mac-bridge |
| **Component** | comms-etl |

**Full message body:**

```markdown
## Request

Please build the comms-etl service per BUILD-SPEC.md.

**Location:** `/home/dshanklin/repos-personal/mac-bridge/comms-etl/`

## Context

The bronze layer is populated and ready:
- 58,385 messages
- 796 chats
- 1,259 handles
- 275 calls
- 1,119 contacts (1,798 phones, 772 emails)

## Deliverables

1. ETL transforms (bronze → silver → gold)
2. MCP server with query tools
3. pyproject.toml with uv config

## Pattern

Follow the Cliff project structure at `/home/dshanklin/repos-meetrhea/cliff-data/`
```

---

## 8. BUILD-SPEC for comms-etl

The detailed build specification is at:
```
/home/dshanklin/repos-personal/mac-bridge/comms-etl/BUILD-SPEC.md
```

### Summary of What to Build

**Project Structure:**
```
comms-etl/
├── pyproject.toml
├── README.md
├── etl/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── bronze_to_silver/
│   │   ├── apple_messages.py
│   │   ├── apple_calls.py
│   │   └── apple_contacts.py
│   ├── silver_to_gold/
│   │   ├── contacts.py
│   │   ├── messages.py
│   │   ├── calls.py
│   │   └── threads.py
│   └── main.py
├── mcp/
│   ├── __init__.py
│   ├── server.py
│   └── tools.py
└── scripts/
    └── run_etl.sh
```

### Key Transformations

#### Bronze → Silver

1. **Messages**: Convert `date_apple` (nanoseconds) to TIMESTAMPTZ, resolve handle_id to identifier
2. **Calls**: Convert `date_apple` (seconds) to TIMESTAMPTZ, derive direction/status
3. **Contacts**: Deduplicate across sources, aggregate phone/email arrays

#### Silver → Gold

1. **Contacts**: Create unified contact records, link identifiers
2. **Messages**: Create unified messages with contact_id and thread_id
3. **Calls**: Create unified calls with contact_id
4. **Threads**: Build conversation threads from chat_guid

### MCP Tools to Implement

```python
comms_messages_list(source, contact, since, limit)
comms_messages_search(query, source, limit)
comms_contacts_lookup(identifier)
comms_contacts_list(limit)
comms_calls_list(direction, status, since, limit)
comms_thread_messages(thread_id, limit)
comms_stats()
```

### Reference Project

Look at Cliff for patterns:
```
/home/dshanklin/repos-meetrhea/cliff-data/
```

---

## 9. How to Communicate Back

When you complete the task (or have questions), send a message back:

```sql
-- Mark the request as in_progress
SELECT argus.update_message_status_auth(
    'ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM',
    'rhea-builder',
    '9c019805-e837-48b4-bc0a-5e420c26a6b1',
    'in_progress'
);

-- When done, send a response
SELECT argus.send_agent_message_auth(
    'ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM',
    'rhea-builder',
    'mac-client',
    'Re: Build comms-etl service',
    E'## Build Complete\n\nCreated:\n- etl/ module\n- mcp/ server\n- pyproject.toml\n\n## Notes\n...',
    'response',
    'normal',
    NULL,
    '9c019805-e837-48b4-bc0a-5e420c26a6b1',  -- Reply to original message
    NULL,
    'mac-bridge',
    'comms-etl',
    ARRAY['completed']
);

-- Mark original as completed
SELECT argus.update_message_status_auth(
    'ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM',
    'rhea-builder',
    '9c019805-e837-48b4-bc0a-5e420c26a6b1',
    'completed'
);
```

---

## 10. File Locations

### On rhea-dev

| Path | Description |
|------|-------------|
| `/home/dshanklin/repos-personal/mac-bridge/` | Main project directory |
| `/home/dshanklin/repos-personal/mac-bridge/comms-etl/` | Where you build the ETL service |
| `/home/dshanklin/repos-personal/mac-bridge/comms-etl/BUILD-SPEC.md` | Detailed build specification |
| `/home/dshanklin/repos-meetrhea/cliff-data/` | Reference project (email sync) |
| `/home/dshanklin/repos-meetrhea/argus/migrations/` | Database migrations |

### Migrations Created

| File | Database | Description |
|------|----------|-------------|
| `007_agent_messages.sql` | argus | Inter-agent messaging tables |
| `007b_auth_functions.sql` | argus | Authentication functions |

---

## 11. Credentials

### comms Database (pg-rhea)

```
Host:     10.0.1.5
Port:     5432
Database: comms
User:     postgres
Password: TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi
```

### Agent API Keys

| Agent | API Key |
|-------|---------|
| mac-client | `ak_PjI82IPXFb3o3K8R6yd4ntT63xwSXjec` |
| rhea-server | `ak_n48Ie6x0DXurg50ywk556p1SJT3N2wAp` |
| rhea-builder | `ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM` |

**Your API key (rhea-builder):** `ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM`

---

## Quick Start Checklist

1. [ ] Read this document completely
2. [ ] Read `/home/dshanklin/repos-personal/mac-bridge/comms-etl/BUILD-SPEC.md`
3. [ ] Check your inbox: `SELECT * FROM argus.get_agent_inbox_auth('ak_DO9+Iyv4DuLietN4mOG+biTZU4VK9QHM', 'rhea-builder');`
4. [ ] Mark message as in_progress
5. [ ] Study Cliff project at `/home/dshanklin/repos-meetrhea/cliff-data/`
6. [ ] Build comms-etl service
7. [ ] Test transforms against bronze data
8. [ ] Send response message back to mac-client
9. [ ] Mark original message as completed

---

## Contact

If you have questions or issues, send a message to `mac-client` via the agent messaging system. The human operator monitors both agents.

---

*Document generated: 2026-01-10*
*From: mac-client (Claude on MacBook)*
*To: rhea-builder (Claude on rhea-dev)*

---
project: mac-bridge
type: architecture
date: 2025-12-18
created: 2025-12-18
status: planning
---

# Mac Bridge: Personal Data Synchronization Infrastructure

## The Grand Vision

A system that syncs all personal data from Daniel's Mac to a centralized PostgreSQL database on rhea-dev, enabling "Reeves in the Cloud" - AI that can manage his life with complete context.

```
┌─────────────────────────────────────────────────────────────────┐
│                         MAC (Local)                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              mac-sync-daemon (launchd)                     │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │  │
│  │  │ Messages │ │  Calls   │ │ Contacts │ │ Calendar │     │  │
│  │  │ Watcher  │ │ Watcher  │ │ Watcher  │ │ Watcher  │     │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘     │  │
│  │       └────────────┴────────────┴────────────┘            │  │
│  │                         │                                  │  │
│  │                   Change Queue                             │  │
│  │                         │                                  │  │
│  │                   Sync Engine ──────────────────────────────────►
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              mac-bridge-mcp (Claude Code)                  │  │
│  │  - Read messages, calls, contacts locally                  │  │
│  │  - Human-in-the-loop confirmation for sends                │  │
│  │  - Smart contact resolution                                │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               │ HTTPS + PostgreSQL wire protocol
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RHEA-DEV (Cloud)                            │
│                      162.220.24.23                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     PostgreSQL                             │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ │  │
│  │  │ messages  │ │   calls   │ │ contacts  │ │ calendar  │ │  │
│  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘ │  │
│  │                         │                                  │  │
│  │              PostgreSQL Triggers & NOTIFY                  │  │
│  │                         │                                  │  │
│  └─────────────────────────┼─────────────────────────────────┘  │
│                            │                                     │
│  ┌─────────────────────────┼─────────────────────────────────┐  │
│  │               Reeves Cloud Service                         │  │
│  │  - Query API for AI assistants                            │  │
│  │  - Proactive insights engine                              │  │
│  │  - Cross-device sync coordination                         │  │
│  │  - Email ingestion (future)                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Sources (macOS)

| Source | Database Path | Key Tables | Priority |
|--------|---------------|------------|----------|
| Messages | `~/Library/Messages/chat.db` | message, handle, chat | P0 |
| Calls | `~/Library/Application Support/CallHistoryDB/CallHistory.storedata` | ZCALLRECORD | P0 |
| Contacts | `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb` | ZABCDRECORD, ZABCDPHONENUMBER, ZABCDEMAILADDRESS | P0 |
| Calendar | `~/Library/Calendars/Calendar.sqlitedb` | ZCALENDARITEM | P1 |
| Reminders | `~/Library/Reminders/Container_v1/Stores/*.sqlite` | ZREMCDREMINDER | P1 |
| Notes | `~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite` | ZICCLOUDSYNCINGOBJECT | P2 |
| Safari History | `~/Library/Safari/History.db` | history_items, history_visits | P2 |

---

## Project Components

### Component 1: `mac-bridge-mcp` (MCP Server for Claude Code)

Local MCP server that provides Claude Code access to Mac data with human-in-the-loop safety.

**Features:**
1. Read messages with contact resolution
2. Read call history with contact resolution
3. Search contacts
4. Send messages WITH confirmation popup
5. Conversation thread view
6. Proactive insights (unanswered messages, missed calls)

### Component 2: `mac-sync-daemon` (Background Sync Service)

launchd daemon that watches macOS databases and syncs changes to PostgreSQL.

**Features:**
1. File system watchers on SQLite databases
2. Change detection (new rows, updates)
3. Queue-based sync with retry logic
4. Secure connection to rhea-dev PostgreSQL
5. Conflict resolution for edits

### Component 3: `rhea-postgres-schema` (Cloud Database)

PostgreSQL schema on rhea-dev that stores synchronized data.

**Features:**
1. Normalized schema for all data types
2. Triggers for change notifications
3. Views for AI-friendly queries
4. Audit logging

### Component 4: `reeves-cloud-api` (Future)

API service on rhea-dev for AI access to synchronized data.

---

## Implementation Phases

### Phase 0: Foundation (This Session)
- [x] Discover macOS database locations
- [x] Understand existing `mac-messages-mcp` architecture
- [x] Query call history and contacts successfully
- [ ] Create project repository structure
- [ ] Write comprehensive implementation checklists

### Phase 1: Local MCP Server (`mac-bridge-mcp`)
- [ ] Scaffold project
- [ ] Port messages functionality from `mac-messages-mcp`
- [ ] Add call history support
- [ ] Add unified contact resolution
- [ ] Add human-in-the-loop confirmation
- [ ] Add proactive insights tool
- [ ] Testing and documentation

### Phase 2: Cloud Database (`rhea-postgres-schema`)
- [ ] Design PostgreSQL schema
- [ ] Set up PostgreSQL on rhea-dev
- [ ] Create tables, indexes, triggers
- [ ] Create AI-friendly views
- [ ] Test with sample data

### Phase 3: Sync Daemon (`mac-sync-daemon`)
- [ ] Create launchd service structure
- [ ] Implement database watchers
- [ ] Implement change detection
- [ ] Implement sync queue
- [ ] Implement PostgreSQL uploader
- [ ] Testing and deployment

### Phase 4: Integration
- [ ] Connect all components
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] Documentation

---

## Detailed Checklists

See separate checklist files:
- `CHECKLIST-01-mac-bridge-mcp.md` - Local MCP server
- `CHECKLIST-02-rhea-postgres-schema.md` - Cloud database
- `CHECKLIST-03-mac-sync-daemon.md` - Background sync service

---

## Key Design Decisions

### 1. Human-in-the-Loop for Sends
Every message send MUST show a native macOS dialog for confirmation. No exceptions.

```applescript
display dialog "Send to " & recipientName & "?" & return & return & messageText ¬
    buttons {"Cancel", "Send"} default button "Send" with title "Mac Bridge"
```

### 2. SQLite WAL Mode Handling
macOS databases use WAL mode. Must handle:
- `-wal` and `-shm` files
- Checkpoint timing
- Read-only access to avoid corruption

### 3. Contact Deduplication
Single canonical contact from multiple sources:
- AddressBook (primary)
- Messages history (fallback names)
- Call history (fallback numbers)

### 4. Sync Strategy
- **Initial sync**: Full table scan, batch insert to PostgreSQL
- **Incremental sync**: Watch for file changes, query new rows only
- **Conflict resolution**: Cloud wins (manual edits on rhea-dev take precedence)

### 5. Security
- PostgreSQL connection over SSH tunnel or SSL
- No credentials in code (use macOS Keychain + environment variables)
- Audit log of all synced data

---

## Repository Structure

```
dshanklin-bv/mac-bridge/
├── README.md
├── CHECKLIST-01-mac-bridge-mcp.md
├── CHECKLIST-02-rhea-postgres-schema.md
├── CHECKLIST-03-mac-sync-daemon.md
├── mac-bridge-mcp/
│   ├── pyproject.toml
│   ├── src/
│   │   └── mac_bridge_mcp/
│   │       ├── __init__.py
│   │       ├── server.py          # FastMCP server
│   │       ├── messages.py        # Messages functionality
│   │       ├── calls.py           # Call history
│   │       ├── contacts.py        # Unified contacts
│   │       ├── insights.py        # Proactive insights
│   │       └── confirmation.py    # Human-in-the-loop
│   └── tests/
├── mac-sync-daemon/
│   ├── pyproject.toml
│   ├── src/
│   │   └── mac_sync_daemon/
│   │       ├── __init__.py
│   │       ├── daemon.py          # Main daemon
│   │       ├── watchers/          # Database watchers
│   │       ├── sync/              # Sync engine
│   │       └── postgres/          # PostgreSQL client
│   ├── launchd/
│   │   └── com.dshanklin.mac-sync-daemon.plist
│   └── tests/
├── rhea-postgres-schema/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   ├── 002_triggers.sql
│   │   └── 003_views.sql
│   └── seed/
└── docs/
    ├── architecture.md
    ├── setup-guide.md
    └── troubleshooting.md
```

---

## Success Criteria

### Phase 1 Complete When:
- [ ] `mac-bridge-mcp` installed in Claude Code
- [ ] Can read last 24h messages with contact names
- [ ] Can read last 7d call history with contact names
- [ ] Can search contacts by name
- [ ] Sending message shows confirmation popup
- [ ] All tests pass

### Phase 2 Complete When:
- [ ] PostgreSQL running on rhea-dev
- [ ] Schema created with all tables
- [ ] Can insert test data
- [ ] Views return expected results
- [ ] Triggers fire correctly

### Phase 3 Complete When:
- [ ] Daemon starts on boot
- [ ] Detects new messages within 30 seconds
- [ ] Syncs to PostgreSQL successfully
- [ ] Handles network failures gracefully
- [ ] Logs are useful for debugging

### Full System Complete When:
- [ ] New message on iPhone appears in rhea-dev PostgreSQL within 2 minutes
- [ ] New call appears in rhea-dev PostgreSQL within 2 minutes
- [ ] Contact updates sync within 5 minutes
- [ ] System runs for 7 days without intervention
- [ ] Can query "who called me this week" from rhea-dev

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| macOS database schema changes | Medium | High | Pin to macOS version, add schema detection |
| Full Disk Access revoked | Low | Critical | Clear error messages, health checks |
| PostgreSQL connection failures | Medium | Medium | Queue with retry, offline mode |
| Data corruption from concurrent access | Low | Critical | Read-only mode, WAL handling |
| Sync gets behind during heavy use | Medium | Low | Batch processing, backpressure |

---

## Timeline

| Phase | Estimated Effort | Dependencies |
|-------|------------------|--------------|
| Phase 1: mac-bridge-mcp | 4-6 hours | None |
| Phase 2: rhea-postgres-schema | 2-3 hours | SSH to rhea-dev |
| Phase 3: mac-sync-daemon | 6-8 hours | Phase 2 |
| Phase 4: Integration | 2-4 hours | All above |

**Total: ~16-20 hours of focused work**

---

## Next Steps

1. Create the `dshanklin-bv/mac-bridge` repository
2. Write detailed checklist for Phase 1 (`mac-bridge-mcp`)
3. Begin implementation

---

*This document is the master plan. Detailed implementation steps are in the CHECKLIST files.*

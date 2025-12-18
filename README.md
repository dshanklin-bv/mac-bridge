# Mac Bridge

Sync macOS data (Messages, Calls, Contacts) to PostgreSQL for AI-powered life management.

## Vision

A personal data synchronization infrastructure that:

1. **Syncs** Messages, Calls, and Contacts from Mac to cloud PostgreSQL
2. **Centralizes** all communication data for AI access
3. **Enables** "Reeves in the Cloud" - AI that manages your life with full context

```
Mac (local)              Cloud (rhea-dev)
┌──────────────┐         ┌──────────────┐
│  Messages    │         │              │
│  Calls       │ ──────► │  PostgreSQL  │ ──────► AI / Reeves
│  Contacts    │  sync   │              │
└──────────────┘         └──────────────┘
```

## Architecture

### mac-sync-daemon (Local)
- Watches macOS SQLite databases for changes
- Queues changes locally (survives restarts)
- Uploads to PostgreSQL on rhea-dev
- **AI-free** - just a data pipeline

### PostgreSQL (Cloud)
- Stores synchronized data
- Triggers for change notifications
- Views for AI-friendly queries
- Contact auto-resolution

### Intelligence (Cloud)
- All analysis happens server-side
- Proactive insights (unanswered messages, missed calls)
- API for AI assistants

## Documentation

- [Master Plan](docs/MASTER-PLAN.md) - Full architecture and vision
- [Checklist 01: MCP Server](docs/CHECKLIST-01-mac-bridge-mcp.md) - Local MCP (optional)
- [Checklist 02: PostgreSQL](docs/CHECKLIST-02-rhea-postgres-schema.md) - Cloud database setup
- [Checklist 03: Sync Daemon](docs/CHECKLIST-03-mac-sync-daemon.md) - Background sync service

## Quick Start

**Recommended order:**

1. **Phase 2** - Set up PostgreSQL on rhea-dev
2. **Phase 3** - Build and deploy sync daemon
3. **Phase 1** - (Optional) Local MCP for Claude Code

See the checklists in `/docs` for detailed implementation steps.

## Data Sources

| Source | macOS Path | Synced |
|--------|------------|--------|
| Messages | `~/Library/Messages/chat.db` | Yes |
| Calls | `~/Library/Application Support/CallHistoryDB/CallHistory.storedata` | Yes |
| Contacts | `~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb` | Yes |
| Calendar | `~/Library/Calendars/Calendar.sqlitedb` | Planned |
| Reminders | `~/Library/Reminders/...` | Planned |

## Requirements

- macOS with Full Disk Access granted
- Python 3.11+
- PostgreSQL on rhea-dev (162.220.24.23)
- SSH access to rhea-dev

## License

Private - Personal use only

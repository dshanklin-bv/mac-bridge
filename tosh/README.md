# Tosh - Mac-Side Data Agent

Tosh is a daemon that runs on the Mac, syncing Apple data (messages, calls, contacts, photos) to the rhea-dev server. It communicates with **reeves** (server-side agent) via the agent messaging system.

## Identity

- **Agent name:** `tosh`
- **Location:** Mac (local machine)
- **Partner agent:** `reeves` (runs on rhea-dev server)
- **Database:** argus (on rhea-dev, accessed via SSH tunnel)

## Daemon Cycle (every 15 minutes)

1. **Sync metadata** - messages, calls, contacts, photos to bronze tables
2. **Transfer local photos** - rsync any pending local photos to server
3. **Download iCloud photos** - batch of 30 per cycle (stream-through pattern)
4. **Check inbox** - look for assignments from reeves
5. **Report health** - write status to argus.agent_health

## Messaging with Reeves

### Reading Messages

```sql
-- SSH to rhea-dev, exec into postgres container
SELECT id, subject, body, created_at
FROM argus.agent_messages
WHERE from_agent = 'reeves' AND to_agent = 'tosh'
ORDER BY created_at DESC LIMIT 5;
```

### Sending Messages

```sql
INSERT INTO argus.agent_messages (
    id, from_agent, to_agent, subject, body,
    priority, message_type, status, created_at
) VALUES (
    gen_random_uuid(),
    'tosh',
    'reeves',
    'Subject here',
    'Message body here (markdown supported)',
    'normal',        -- normal, high, urgent
    'status_update', -- status_update, proposal, question, assignment
    'sent',
    NOW()
);
```

### Message Types

| Type | Use |
|------|-----|
| `status_update` | Reporting progress or completion |
| `proposal` | Suggesting a plan for approval |
| `question` | Asking for clarification |
| `assignment` | Task assignment (usually from reeves) |

## Health Reporting

After each daemon cycle, report health to `argus.agent_health`:

```sql
INSERT INTO argus.agent_health (
    agent_name, check_time, status, last_sync_success,
    sync_type, rows_synced, files_transferred,
    errors, checks_passed, metadata
) VALUES (
    'tosh', NOW(), 'healthy', NOW(),
    'daemon_cycle', 100, 5,
    '[]'::jsonb,
    '{"ssh": true, "db_read": true, "local_health": true}'::jsonb,
    '{}'::jsonb
);
```

### Status Values

| Status | Meaning |
|--------|---------|
| `healthy` | All checks passed |
| `degraded` | Some checks failed but still running |
| `unhealthy` | Critical failures |
| `unknown` | Unable to determine |

### Checks to Perform

- `ssh` - Can reach rhea-dev (implicit if query works)
- `db_read` - Can SELECT from database
- `local_health` - Local health.json shows healthy

Reeves monitors this table and alerts if:
- Status != healthy
- No entry for 30+ minutes

## CLI Commands

```bash
# Sync all sources
python -m tosh.cli.sync --source all

# Photo operations
python -m tosh.cli.photos stats      # Show photo sync status
python -m tosh.cli.photos transfer   # Transfer local photos
python -m tosh.cli.photos download   # Download iCloud batch
python -m tosh.cli.photos overnight  # Aggressive iCloud download

# Health
python -m tosh.cli.health            # Show local health status
python -m tosh.cli.health --report   # Report to argus.agent_health

# Inbox
python -m tosh.cli.inbox             # Check for assignments from reeves
```

## Database Connection

Tosh connects to rhea-dev via SSH tunnel:

- **Local port:** 15432
- **Remote:** rhea-dev:5432 (postgres container)
- **Database:** argus (for messaging, health), bronze schema for sync data

The tunnel is managed by launchd: `com.tosh.tunnel.plist`

## File Locations

| Path | Purpose |
|------|---------|
| `~/.tosh/config.yaml` | Configuration |
| `~/.tosh/health.json` | Local health status |
| `/tmp/tosh_icloud_export/` | Temp dir for iCloud downloads |

## Server Paths

Photos are transferred to:
```
rhea-dev:/home/dshanklin/data/photos/originals/{YYYY}/{MM}/{UUID}_{filename}.{ext}
```

## Key Principles

1. **Stream-through for photos** - Download to temp, transfer to server, delete local. Don't fill Mac storage.

2. **Fail gracefully** - Each daemon step runs independently. One failure doesn't block others.

3. **Report health** - Always report status so reeves can monitor.

4. **Message reeves** - For status updates, questions, or proposals. Check inbox for assignments.

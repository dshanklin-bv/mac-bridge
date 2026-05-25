# Agent Watcher

Lightweight daemon that polls for inter-agent messages and spawns Claude Code to handle them.

## How It Works

```
CRON (every 5 min)
       │
       ▼
   watcher.py
       │
       ▼
 Check argus.agent_messages for pending messages
       │
       ├── No messages → exit
       │
       └── Messages found
              │
              ▼
      Start agent_session (logging)
              │
              ▼
      Spawn Claude Code with inbox context
              │
              ▼
      Claude reads messages, takes actions, sends replies
              │
              ▼
      End agent_session (outcome, summary)
```

## The Key Insight

AI agents stop when conversations end. The cron job is the heartbeat that maintains agency across sessions. Messages provide continuity - they're the persistent state that bridges sessions.

## Installation

```bash
cd ~/repos-personal/mac-bridge/agent-watcher
pip install -r requirements.txt
```

## Configuration

Environment variables (or defaults in watcher.py):

| Variable | Default | Description |
|----------|---------|-------------|
| AGENT_ID | mac-client | Your agent identity |
| AGENT_API_KEY | (set in code) | API key for message auth |
| SSH_HOST | rhea-dev | SSH jump host |
| SSH_USER | dshanklin | SSH username |
| PG_HOST | 10.0.1.5 | Postgres host (via tunnel) |
| PG_DATABASE | argus | Database name |

## Usage

### Manual Run

```bash
python3 watcher.py
```

### Cron Setup (every 5 minutes)

```bash
crontab -e
# Add:
*/5 * * * * cd ~/repos-personal/mac-bridge/agent-watcher && python3 watcher.py >> ~/Library/Logs/mac-bridge/agent-watcher-cron.log 2>&1
```

### Launchd Setup (macOS native)

Use daemon-mgr to install:

```bash
cd ~/repos-personal/mac-bridge/daemon-mgr
python3 daemonctl.py install agent-watcher
```

## Observability

Sessions are logged to `argus.agent_sessions`:

```sql
SELECT * FROM argus.v_agent_session_activity
WHERE agent_id = 'mac-client'
ORDER BY started_at DESC;
```

Logs: `~/Library/Logs/mac-bridge/agent-watcher.log`

## The Bigger Picture

This daemon enables:

1. **Async task handoffs** - Server sends "build X", Mac wakes up and builds
2. **Autonomous operation** - Agents coax each other forward via messages
3. **Event-driven AI** - AI only runs when there's work (zero idle cost)
4. **Future: live mode** - Messages could establish real-time channels

See `SERVER-HANDOFF.md` and argus devlogs for architecture details.

# Mac Bridge

Personal infrastructure for syncing Mac data to the cloud and enabling remote access.

## Quick Start

```bash
cd ~/repos-personal/mac-bridge

# Check service status
python3 daemon-mgr/daemonctl.py status

# Install services
python3 daemon-mgr/daemonctl.py install

# Launch menu bar app
python3 ip-reporter/menubar.py

# From rhea-dev, connect to Mac:
ssh -p 2222 dshanklinbv@localhost
```

## Components

| Component | Purpose | Status |
|-----------|---------|--------|
| **reverse-tunnel** | Persistent SSH tunnel to rhea-dev | ✅ Working |
| **ip-reporter** | Reports Mac's IP to cloud servers | ✅ Working |
| **menubar** | Menu bar status app | ✅ Working |
| **daemon-mgr** | CLI for managing LaunchAgents | ✅ Working |
| **mac-sync-daemon** | Syncs Messages/Calls/Contacts | 🚧 Planned |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  MAC (behind NAT)                                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  🌉 Menu Bar App                                          │  │
│  │  ├─ 📍 IP: 10.0.250.3 (Public: 12.228.203.178)           │  │
│  │  ├─ 🔗 Tunnel: ✅ Connected (port 2222)                   │  │
│  │  ├─ 🖥️ rhea-dev: ✅ | jetta-dev: ✅                       │  │
│  │  └─ 📚 Help / Docs / Logs                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐                      │
│  │ reverse-tunnel  │  │  ip-reporter    │                      │
│  │ (autossh)       │  │  (python)       │                      │
│  └────────┬────────┘  └─────────────────┘                      │
│           │                                                     │
│           │ SSH tunnel (Mac initiates, always on)               │
└───────────┼─────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  RHEA-DEV (162.220.24.23)                                       │
│                                                                 │
│  localhost:2222 ──► Mac's SSH (port 22)                        │
│                                                                 │
│  $ ssh -p 2222 dshanklinbv@localhost  # connects to Mac!       │
└─────────────────────────────────────────────────────────────────┘
```

## Menu Bar App

The menu bar app shows status at a glance:

- **🌉** = All systems operational
- **🌉⚠️** = Tunnel ok, server issue
- **🌉❌** = Tunnel down

Click to open menu, click "Refresh Status" to check connectivity.

Features:
- Current IP (local and public)
- Tunnel status (connected/disconnected)
- Server status (rhea-dev, jetta-dev)
- Restart tunnel
- Report IP now
- View logs
- SSH help

```bash
# Run manually
python3 ip-reporter/menubar.py

# Install as LaunchAgent (starts at login)
python3 daemon-mgr/daemonctl.py install ip-reporter-menubar
```

## Services

### reverse-tunnel

Maintains a persistent reverse SSH tunnel using `autossh`.

```bash
# From rhea-dev:
ssh -p 2222 dshanklinbv@localhost
```

**Requirements:**
- `brew install autossh`
- SSH key auth for rhea-dev
- `~/.ssh/config` entry for `rhea-dev`

### ip-reporter

Reports Mac's current IP to configured servers.

```bash
python3 ip-reporter/reporter.py --status   # Show current IP
python3 ip-reporter/reporter.py --once     # Report now
python3 ip-reporter/reporter.py            # Run continuously
```

### daemon-mgr

Unified CLI for managing all mac-bridge services.

```bash
python3 daemon-mgr/daemonctl.py status                    # Show all
python3 daemon-mgr/daemonctl.py start reverse-tunnel      # Start
python3 daemon-mgr/daemonctl.py stop reverse-tunnel       # Stop
python3 daemon-mgr/daemonctl.py restart reverse-tunnel    # Restart
python3 daemon-mgr/daemonctl.py install                   # Install all
python3 daemon-mgr/daemonctl.py logs reverse-tunnel       # View logs
```

## Installation

### Prerequisites

```bash
# Install autossh
brew install autossh

# Install Python dependencies
pip install rumps pyyaml

# SSH config for rhea-dev
cat >> ~/.ssh/config << 'EOF'
Host rhea-dev
    HostName 162.220.24.23
    User dshanklinbv
    IdentityFile ~/.ssh/id_ed25519
EOF
```

### Install Services

```bash
cd ~/repos-personal/mac-bridge

# Install all services as LaunchAgents
python3 daemon-mgr/daemonctl.py install

# Verify
python3 daemon-mgr/daemonctl.py status
```

### Verify Tunnel

From rhea-dev:
```bash
ssh -p 2222 dshanklinbv@localhost
```

## Logs

```bash
# View logs directory
open ~/Library/Logs/mac-bridge/

# Tail specific log
tail -f ~/Library/Logs/mac-bridge/reverse-tunnel.log
```

## Troubleshooting

### Tunnel not connecting

1. Check SSH key auth: `ssh rhea-dev echo ok`
2. Check autossh: `which autossh`
3. View logs: `python3 daemon-mgr/daemonctl.py logs reverse-tunnel`
4. Restart: `python3 daemon-mgr/daemonctl.py restart reverse-tunnel`

### Menu bar app won't start

1. Check rumps installed: `pip install rumps`
2. Run manually to see errors: `python3 ip-reporter/menubar.py`

## Future Plans

See [docs/MASTER-PLAN.md](docs/MASTER-PLAN.md) for the full roadmap:
- Messages/Calls/Contacts sync to PostgreSQL
- MCP server for Claude Code integration

# rhea-dev PostgreSQL Status

**Last Updated:** 2025-12-18
**Server:** 162.220.24.23 (rhea-dev)

## Current Setup

PostgreSQL runs via **Docker containers** managed by Coolify, not as a system service.

### Existing Containers

| Container | Image | Purpose | Port |
|-----------|-------|---------|------|
| `ourotters-postgres` | postgres:16-alpine | OurOtters project | 5432 (public) |
| `qcwggosccso88ogww4w8soss` | postgres:17-alpine | Coolify managed | internal |
| `lg08owokskkwgkswookcw0kk` | postgres:17-alpine | Coolify managed | internal |
| `coolify-db` | postgres:15-alpine | Coolify platform | internal |

**Note:** None of these are suitable for mac-bridge. Personal life data requires complete isolation.

---

## Mac-Bridge Database Requirements

**Database Name:** `djs_life` or `reeves_data`
**User:** `daniel` (sole owner)
**Access:** Only Daniel James Shanklin
**Purpose:** Personal communication data (Messages, Calls, Contacts)

### Security Requirements

- [ ] Dedicated container (not shared with any project)
- [ ] Strong password stored in macOS Keychain only
- [ ] SSL/TLS for connections
- [ ] Firewall rules limiting access to Daniel's IPs
- [ ] Regular encrypted backups

---

## Setup Plan: Dedicated Container

### Step 1: Create Docker Compose File

```yaml
# ~/repos-personal/mac-bridge-db/docker-compose.yml
version: '3.8'
services:
  djs-life-db:
    image: postgres:17-alpine
    container_name: djs-life-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: daniel
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: djs_life
    volumes:
      - djs_life_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"  # Different port to avoid conflict
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U daniel -d djs_life"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  djs_life_data:
```

### Step 2: Create .env File (on rhea-dev only)

```bash
# ~/repos-personal/mac-bridge-db/.env
POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>
```

### Step 3: Start Container

```bash
ssh rhea-dev
cd ~/repos-personal/mac-bridge-db
docker compose up -d
```

### Step 4: Verify Connection

```bash
# From Mac
psql -h 162.220.24.23 -p 5433 -U daniel -d djs_life -c 'SELECT 1;'
```

### Step 5: Store Password in Keychain

```bash
# On Mac
security add-generic-password -a "mac-sync-daemon" -s "djs-life-postgres" -w "YOUR_PASSWORD"
```

---

## Connection Details (after setup)

| Field | Value |
|-------|-------|
| Host | 162.220.24.23 |
| Port | **5433** |
| Database | djs_life |
| User | daniel |
| Password | (in macOS Keychain) |

**Connection String:**
```
postgresql://daniel:PASSWORD@162.220.24.23:5433/djs_life
```

---

## Next Steps

- [ ] SSH to rhea-dev
- [ ] Create `~/repos-personal/mac-bridge-db/` directory
- [ ] Create docker-compose.yml
- [ ] Generate secure password
- [ ] Start container
- [ ] Open port 5433 in firewall
- [ ] Test connection from Mac
- [ ] Run schema migrations
- [ ] Store password in macOS Keychain

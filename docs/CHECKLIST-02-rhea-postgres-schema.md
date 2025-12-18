---
project: mac-bridge
type: checklist
phase: 2
component: rhea-postgres-schema
date: 2025-12-18
status: not-started
---

# CHECKLIST 02: rhea-postgres-schema (Cloud Database)

## Overview

Set up PostgreSQL on rhea-dev to store synchronized personal data from Mac. This is the central brain for "Reeves in the Cloud."

**Estimated Time:** 2-3 hours
**Dependencies:** SSH access to rhea-dev (162.220.24.23)
**Output:** Working PostgreSQL database with schema, triggers, and views

---

## Pre-Flight Checks

- [ ] **Check 0.1**: SSH to rhea-dev works
  ```bash
  ssh rhea-dev "echo 'Connected'"
  # Expected: Connected
  ```

- [ ] **Check 0.2**: Check if PostgreSQL is installed
  ```bash
  ssh rhea-dev "which psql && psql --version"
  ```
  **Record:** PostgreSQL version: _________________
  **If not installed, proceed to Section 1.**

---

## Section 1: PostgreSQL Installation (if needed)

### 1.1 Install PostgreSQL on rhea-dev

- [ ] **Task 1.1.1**: Install PostgreSQL
  ```bash
  ssh rhea-dev "sudo apt update && sudo apt install -y postgresql postgresql-contrib"
  ```

- [ ] **Task 1.1.2**: Start PostgreSQL service
  ```bash
  ssh rhea-dev "sudo systemctl start postgresql && sudo systemctl enable postgresql"
  ```

- [ ] **Task 1.1.3**: Verify installation
  ```bash
  ssh rhea-dev "sudo -u postgres psql -c 'SELECT version();'"
  ```
  **Record:** PostgreSQL running? [ ] Yes [ ] No

### 1.2 Create Database and User

- [ ] **Task 1.2.1**: Create database user
  ```bash
  ssh rhea-dev "sudo -u postgres psql -c \"CREATE USER mac_bridge WITH PASSWORD 'CHANGE_ME_SECURE_PASSWORD';\""
  ```
  **IMPORTANT:** Record password securely in macOS Keychain

- [ ] **Task 1.2.2**: Create database
  ```bash
  ssh rhea-dev "sudo -u postgres psql -c \"CREATE DATABASE reeves_data OWNER mac_bridge;\""
  ```

- [ ] **Task 1.2.3**: Grant permissions
  ```bash
  ssh rhea-dev "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE reeves_data TO mac_bridge;\""
  ```

- [ ] **Task 1.2.4**: Test connection
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -c 'SELECT 1;'"
  ```
  **Record:** Connection works? [ ] Yes [ ] No

### 1.3 Configure Remote Access (for sync daemon)

- [ ] **Task 1.3.1**: Edit `postgresql.conf` to listen on all interfaces
  ```bash
  ssh rhea-dev "sudo sed -i \"s/#listen_addresses = 'localhost'/listen_addresses = '*'/\" /etc/postgresql/*/main/postgresql.conf"
  ```

- [ ] **Task 1.3.2**: Edit `pg_hba.conf` to allow remote connections
  ```bash
  ssh rhea-dev "echo 'host reeves_data mac_bridge 0.0.0.0/0 scram-sha-256' | sudo tee -a /etc/postgresql/*/main/pg_hba.conf"
  ```

- [ ] **Task 1.3.3**: Restart PostgreSQL
  ```bash
  ssh rhea-dev "sudo systemctl restart postgresql"
  ```

- [ ] **Task 1.3.4**: Test remote connection from Mac
  ```bash
  psql -h 162.220.24.23 -U mac_bridge -d reeves_data -c 'SELECT 1;'
  ```
  **Record:** Remote connection works? [ ] Yes [ ] No
  **If No, check firewall:** `ssh rhea-dev "sudo ufw allow 5432/tcp"`

---

## Section 2: Schema Design

### 2.1 Create Migration Files

- [ ] **Task 2.1.1**: Create migrations directory locally
  ```bash
  mkdir -p ~/repos/mac-bridge/rhea-postgres-schema/migrations
  ```

- [ ] **Task 2.1.2**: Create initial schema migration
  ```sql
  -- migrations/001_initial_schema.sql

  -- Enable UUID extension
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

  -- Device tracking (for multi-device sync)
  CREATE TABLE devices (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      device_name VARCHAR(255) NOT NULL,
      device_type VARCHAR(50) NOT NULL,  -- 'mac', 'iphone', 'ipad'
      last_sync TIMESTAMP WITH TIME ZONE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      is_active BOOLEAN DEFAULT TRUE
  );

  -- Contacts (canonical contact records)
  CREATE TABLE contacts (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      first_name VARCHAR(255),
      last_name VARCHAR(255),
      organization VARCHAR(255),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      source_device_id UUID REFERENCES devices(id),
      source_record_id VARCHAR(255),  -- Original ID from source system
      UNIQUE(source_device_id, source_record_id)
  );

  -- Contact phone numbers (many-to-one with contacts)
  CREATE TABLE contact_phones (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
      phone_number VARCHAR(50) NOT NULL,
      phone_normalized VARCHAR(20) NOT NULL,  -- Digits only
      label VARCHAR(50),  -- 'mobile', 'home', 'work'
      is_primary BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  );
  CREATE INDEX idx_contact_phones_normalized ON contact_phones(phone_normalized);

  -- Contact emails (many-to-one with contacts)
  CREATE TABLE contact_emails (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
      email VARCHAR(255) NOT NULL,
      email_normalized VARCHAR(255) NOT NULL,  -- Lowercase
      label VARCHAR(50),
      is_primary BOOLEAN DEFAULT FALSE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
  );
  CREATE INDEX idx_contact_emails_normalized ON contact_emails(email_normalized);

  -- Messages
  CREATE TABLE messages (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      source_device_id UUID REFERENCES devices(id),
      source_message_id VARCHAR(255),  -- Original ROWID from Messages.db
      handle_identifier VARCHAR(255),  -- Phone/email of other party
      contact_id UUID REFERENCES contacts(id),  -- Resolved contact
      is_from_me BOOLEAN NOT NULL,
      message_text TEXT,
      message_date TIMESTAMP WITH TIME ZONE NOT NULL,
      is_read BOOLEAN DEFAULT FALSE,
      is_delivered BOOLEAN DEFAULT FALSE,
      chat_identifier VARCHAR(255),  -- For group chats
      chat_display_name VARCHAR(255),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      UNIQUE(source_device_id, source_message_id)
  );
  CREATE INDEX idx_messages_date ON messages(message_date DESC);
  CREATE INDEX idx_messages_handle ON messages(handle_identifier);
  CREATE INDEX idx_messages_contact ON messages(contact_id);

  -- Call history
  CREATE TABLE calls (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      source_device_id UUID REFERENCES devices(id),
      source_call_id VARCHAR(255),  -- Original ROWID from CallHistory
      phone_number VARCHAR(50),
      phone_normalized VARCHAR(20),
      contact_id UUID REFERENCES contacts(id),  -- Resolved contact
      call_date TIMESTAMP WITH TIME ZONE NOT NULL,
      duration_seconds INTEGER,
      is_outgoing BOOLEAN NOT NULL,
      is_answered BOOLEAN NOT NULL,
      call_type VARCHAR(20),  -- 'voice', 'facetime_audio', 'facetime_video'
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      UNIQUE(source_device_id, source_call_id)
  );
  CREATE INDEX idx_calls_date ON calls(call_date DESC);
  CREATE INDEX idx_calls_phone ON calls(phone_normalized);
  CREATE INDEX idx_calls_contact ON calls(contact_id);

  -- Sync log (for debugging and auditing)
  CREATE TABLE sync_log (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      device_id UUID REFERENCES devices(id),
      sync_type VARCHAR(50) NOT NULL,  -- 'messages', 'calls', 'contacts'
      records_synced INTEGER,
      started_at TIMESTAMP WITH TIME ZONE NOT NULL,
      completed_at TIMESTAMP WITH TIME ZONE,
      status VARCHAR(20) NOT NULL,  -- 'started', 'completed', 'failed'
      error_message TEXT
  );
  CREATE INDEX idx_sync_log_device ON sync_log(device_id, started_at DESC);
  ```

- [ ] **Task 2.1.3**: Create triggers migration
  ```sql
  -- migrations/002_triggers.sql

  -- Function to update updated_at timestamp
  CREATE OR REPLACE FUNCTION update_updated_at()
  RETURNS TRIGGER AS $$
  BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  -- Apply to contacts table
  CREATE TRIGGER contacts_updated_at
      BEFORE UPDATE ON contacts
      FOR EACH ROW
      EXECUTE FUNCTION update_updated_at();

  -- Function to notify on new messages
  CREATE OR REPLACE FUNCTION notify_new_message()
  RETURNS TRIGGER AS $$
  BEGIN
      PERFORM pg_notify('new_message', json_build_object(
          'id', NEW.id,
          'handle', NEW.handle_identifier,
          'is_from_me', NEW.is_from_me,
          'date', NEW.message_date
      )::text);
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER messages_notify
      AFTER INSERT ON messages
      FOR EACH ROW
      EXECUTE FUNCTION notify_new_message();

  -- Function to notify on new calls
  CREATE OR REPLACE FUNCTION notify_new_call()
  RETURNS TRIGGER AS $$
  BEGIN
      PERFORM pg_notify('new_call', json_build_object(
          'id', NEW.id,
          'phone', NEW.phone_number,
          'is_outgoing', NEW.is_outgoing,
          'is_answered', NEW.is_answered,
          'date', NEW.call_date
      )::text);
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER calls_notify
      AFTER INSERT ON calls
      FOR EACH ROW
      EXECUTE FUNCTION notify_new_call();

  -- Function to auto-resolve contact_id on message insert
  CREATE OR REPLACE FUNCTION resolve_message_contact()
  RETURNS TRIGGER AS $$
  DECLARE
      resolved_contact_id UUID;
      normalized_phone VARCHAR(20);
  BEGIN
      -- Normalize the handle identifier
      normalized_phone := regexp_replace(NEW.handle_identifier, '[^0-9]', '', 'g');

      -- Try to find matching contact
      SELECT c.id INTO resolved_contact_id
      FROM contacts c
      JOIN contact_phones cp ON c.id = cp.contact_id
      WHERE cp.phone_normalized = normalized_phone
         OR cp.phone_normalized = '1' || normalized_phone
         OR '1' || cp.phone_normalized = normalized_phone
      LIMIT 1;

      NEW.contact_id := resolved_contact_id;
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER messages_resolve_contact
      BEFORE INSERT ON messages
      FOR EACH ROW
      EXECUTE FUNCTION resolve_message_contact();

  -- Same for calls
  CREATE OR REPLACE FUNCTION resolve_call_contact()
  RETURNS TRIGGER AS $$
  DECLARE
      resolved_contact_id UUID;
  BEGIN
      SELECT c.id INTO resolved_contact_id
      FROM contacts c
      JOIN contact_phones cp ON c.id = cp.contact_id
      WHERE cp.phone_normalized = NEW.phone_normalized
         OR cp.phone_normalized = '1' || NEW.phone_normalized
         OR '1' || cp.phone_normalized = NEW.phone_normalized
      LIMIT 1;

      NEW.contact_id := resolved_contact_id;
      RETURN NEW;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER calls_resolve_contact
      BEFORE INSERT ON calls
      FOR EACH ROW
      EXECUTE FUNCTION resolve_call_contact();
  ```

- [ ] **Task 2.1.4**: Create views migration
  ```sql
  -- migrations/003_views.sql

  -- View: Recent messages with contact names
  CREATE OR REPLACE VIEW v_messages_with_contacts AS
  SELECT
      m.id,
      m.message_date,
      m.message_text,
      m.is_from_me,
      m.handle_identifier,
      COALESCE(
          CONCAT_WS(' ', c.first_name, c.last_name),
          m.handle_identifier
      ) AS contact_name,
      c.id AS contact_id,
      m.chat_display_name
  FROM messages m
  LEFT JOIN contacts c ON m.contact_id = c.id
  ORDER BY m.message_date DESC;

  -- View: Recent calls with contact names
  CREATE OR REPLACE VIEW v_calls_with_contacts AS
  SELECT
      ca.id,
      ca.call_date,
      ca.phone_number,
      ca.duration_seconds,
      ca.is_outgoing,
      ca.is_answered,
      ca.call_type,
      COALESCE(
          CONCAT_WS(' ', c.first_name, c.last_name),
          ca.phone_number
      ) AS contact_name,
      c.id AS contact_id,
      CASE
          WHEN ca.is_outgoing THEN 'Outgoing'
          ELSE 'Incoming'
      END AS direction,
      CASE
          WHEN ca.is_answered THEN 'Answered'
          WHEN ca.is_outgoing THEN 'Not Answered'
          ELSE 'Missed'
      END AS status
  FROM calls ca
  LEFT JOIN contacts c ON ca.contact_id = c.id
  ORDER BY ca.call_date DESC;

  -- View: Unanswered messages (for insights)
  CREATE OR REPLACE VIEW v_unanswered_messages AS
  WITH last_messages AS (
      SELECT
          handle_identifier,
          MAX(message_date) FILTER (WHERE NOT is_from_me) AS last_received,
          MAX(message_date) FILTER (WHERE is_from_me) AS last_sent
      FROM messages
      WHERE message_date > NOW() - INTERVAL '48 hours'
      GROUP BY handle_identifier
  )
  SELECT
      lm.handle_identifier,
      lm.last_received,
      lm.last_sent,
      COALESCE(
          CONCAT_WS(' ', c.first_name, c.last_name),
          lm.handle_identifier
      ) AS contact_name
  FROM last_messages lm
  LEFT JOIN contact_phones cp ON cp.phone_normalized = regexp_replace(lm.handle_identifier, '[^0-9]', '', 'g')
  LEFT JOIN contacts c ON cp.contact_id = c.id
  WHERE lm.last_received > COALESCE(lm.last_sent, '1970-01-01'::timestamp);

  -- View: Unreturned calls (for insights)
  CREATE OR REPLACE VIEW v_unreturned_calls AS
  WITH call_pairs AS (
      SELECT
          phone_normalized,
          MAX(call_date) FILTER (WHERE NOT is_outgoing AND NOT is_answered) AS last_missed,
          MAX(call_date) FILTER (WHERE is_outgoing) AS last_outgoing
      FROM calls
      WHERE call_date > NOW() - INTERVAL '48 hours'
      GROUP BY phone_normalized
  )
  SELECT
      cp.phone_normalized,
      cp.last_missed,
      cp.last_outgoing,
      COALESCE(
          CONCAT_WS(' ', c.first_name, c.last_name),
          cp.phone_normalized
      ) AS contact_name
  FROM call_pairs cp
  LEFT JOIN contact_phones cph ON cph.phone_normalized = cp.phone_normalized
  LEFT JOIN contacts c ON cph.contact_id = c.id
  WHERE cp.last_missed > COALESCE(cp.last_outgoing, '1970-01-01'::timestamp);

  -- View: Communication summary
  CREATE OR REPLACE VIEW v_communication_summary AS
  SELECT
      (SELECT COUNT(*) FROM messages WHERE message_date > NOW() - INTERVAL '24 hours' AND NOT is_from_me) AS messages_received_24h,
      (SELECT COUNT(*) FROM messages WHERE message_date > NOW() - INTERVAL '24 hours' AND is_from_me) AS messages_sent_24h,
      (SELECT COUNT(*) FROM calls WHERE call_date > NOW() - INTERVAL '24 hours' AND NOT is_outgoing) AS calls_received_24h,
      (SELECT COUNT(*) FROM calls WHERE call_date > NOW() - INTERVAL '24 hours' AND is_outgoing) AS calls_made_24h,
      (SELECT COUNT(*) FROM calls WHERE call_date > NOW() - INTERVAL '24 hours' AND NOT is_outgoing AND NOT is_answered) AS missed_calls_24h,
      (SELECT COUNT(*) FROM v_unanswered_messages) AS unanswered_count,
      (SELECT COUNT(*) FROM v_unreturned_calls) AS unreturned_calls_count;
  ```

### 2.2 Apply Migrations

- [ ] **Task 2.2.1**: Copy migrations to rhea-dev
  ```bash
  scp -r ~/repos/mac-bridge/rhea-postgres-schema/migrations rhea-dev:~/
  ```

- [ ] **Task 2.2.2**: Apply initial schema
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -f ~/migrations/001_initial_schema.sql"
  ```
  **Record:** Schema created without errors? [ ] Yes [ ] No

- [ ] **Task 2.2.3**: Apply triggers
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -f ~/migrations/002_triggers.sql"
  ```
  **Record:** Triggers created without errors? [ ] Yes [ ] No

- [ ] **Task 2.2.4**: Apply views
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -f ~/migrations/003_views.sql"
  ```
  **Record:** Views created without errors? [ ] Yes [ ] No

---

## Section 3: Testing

### 3.1 Schema Verification

- [ ] **Test 3.1.1**: Verify tables exist
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -c '\dt'"
  ```
  **Record:** Tables visible:
  - [ ] devices
  - [ ] contacts
  - [ ] contact_phones
  - [ ] contact_emails
  - [ ] messages
  - [ ] calls
  - [ ] sync_log

- [ ] **Test 3.1.2**: Verify views exist
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -c '\dv'"
  ```
  **Record:** Views visible:
  - [ ] v_messages_with_contacts
  - [ ] v_calls_with_contacts
  - [ ] v_unanswered_messages
  - [ ] v_unreturned_calls
  - [ ] v_communication_summary

### 3.2 Insert Test Data

- [ ] **Test 3.2.1**: Insert test device
  ```sql
  INSERT INTO devices (device_name, device_type)
  VALUES ('Daniel MacBook Pro', 'mac')
  RETURNING id;
  ```
  **Record:** Device ID: _________________

- [ ] **Test 3.2.2**: Insert test contact
  ```sql
  INSERT INTO contacts (first_name, last_name, source_device_id, source_record_id)
  VALUES ('Test', 'Contact', 'DEVICE_ID', 'test-001')
  RETURNING id;

  INSERT INTO contact_phones (contact_id, phone_number, phone_normalized, label, is_primary)
  VALUES ('CONTACT_ID', '+1 (555) 123-4567', '15551234567', 'mobile', true);
  ```
  **Record:** Contact created? [ ] Yes [ ] No

- [ ] **Test 3.2.3**: Insert test message and verify contact resolution
  ```sql
  INSERT INTO messages (source_device_id, source_message_id, handle_identifier, is_from_me, message_text, message_date)
  VALUES ('DEVICE_ID', 'test-msg-001', '+15551234567', false, 'Test message', NOW())
  RETURNING id, contact_id;
  ```
  **Record:** contact_id was auto-populated? [ ] Yes [ ] No

- [ ] **Test 3.2.4**: Test views
  ```sql
  SELECT * FROM v_messages_with_contacts LIMIT 5;
  SELECT * FROM v_communication_summary;
  ```
  **Record:** Views return expected data? [ ] Yes [ ] No

### 3.3 Test NOTIFY Triggers

- [ ] **Test 3.3.1**: Listen for notifications (in one terminal)
  ```bash
  ssh rhea-dev "PGPASSWORD='CHANGE_ME' psql -U mac_bridge -d reeves_data -c 'LISTEN new_message; LISTEN new_call;'"
  ```

- [ ] **Test 3.3.2**: Insert message and verify notification (in another terminal)
  ```sql
  INSERT INTO messages (source_device_id, source_message_id, handle_identifier, is_from_me, message_text, message_date)
  VALUES ('DEVICE_ID', 'test-msg-002', '+15559999999', true, 'Trigger test', NOW());
  ```
  **Record:** Notification received in first terminal? [ ] Yes [ ] No

---

## Section 4: Cleanup Test Data

- [ ] **Task 4.1**: Remove test data
  ```sql
  DELETE FROM messages WHERE source_message_id LIKE 'test-%';
  DELETE FROM contacts WHERE source_record_id LIKE 'test-%';
  DELETE FROM devices WHERE device_name = 'Daniel MacBook Pro';
  ```

---

## Completion Checklist

- [ ] PostgreSQL installed and running on rhea-dev
- [ ] Database `reeves_data` created
- [ ] User `mac_bridge` can connect
- [ ] Remote connection from Mac works
- [ ] All tables created
- [ ] All triggers created and working
- [ ] All views created and returning data
- [ ] Contact auto-resolution trigger works
- [ ] NOTIFY triggers fire on insert

---

## Recording Section

**Date Started:** _________________
**Date Completed:** _________________

**PostgreSQL Version:** _________________
**Database Password Stored:** [ ] macOS Keychain [ ] Other: _________________

**Connection String:**
```
postgresql://mac_bridge:PASSWORD@162.220.24.23:5432/reeves_data
```

**Issues Encountered:**
1. _________________
2. _________________

---

*This checklist is part of the Mac Bridge project. See `2025-12-18-mac-bridge-project-master-plan.md` for the full plan.*

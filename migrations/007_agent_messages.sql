-- Migration 007: Inter-Agent Messaging System
-- Enables asynchronous communication between AI agents across the rhea ecosystem
-- Similar to email: from, to, subject, body, threading, labels

-- ============================================================================
-- AGENT MESSAGES TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS argus.agent_messages (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id TEXT UNIQUE DEFAULT 'msg_' || gen_random_uuid()::text,

    -- Envelope (email-like)
    from_agent TEXT NOT NULL REFERENCES argus.agents(id),
    to_agent TEXT REFERENCES argus.agents(id),  -- NULL = broadcast to all
    cc_agents TEXT[],                            -- Carbon copy

    -- Threading
    thread_id TEXT,                              -- Groups related messages
    reply_to_id UUID REFERENCES argus.agent_messages(id),
    thread_subject TEXT,                         -- Original subject for thread

    -- Headers
    subject TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',              -- critical, high, normal, low
    message_type TEXT NOT NULL,                  -- request, response, notification,
                                                 -- question, error, status, heartbeat

    -- Body
    body TEXT,                                   -- Markdown content
    attachments JSONB DEFAULT '[]',              -- [{name, type, path, content}]

    -- Context (what is this about?)
    related_project TEXT,                        -- 'mac-bridge', 'cliff', 'ansel'
    related_component TEXT,                      -- 'comms-etl', 'sync-daemon'
    related_entity_type TEXT,                    -- 'ticket', 'devlog', 'initiative'
    related_entity_id UUID,                      -- FK to related entity

    -- Action tracking
    action_requested TEXT,                       -- 'build', 'review', 'deploy', 'fix', 'info'
    action_deadline TIMESTAMPTZ,                 -- When action is needed by

    -- State
    status TEXT DEFAULT 'pending',               -- pending, read, in_progress,
                                                 -- completed, failed, deferred, archived
    read_at TIMESTAMPTZ,
    actioned_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Search
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(body, '')), 'B')
    ) STORED,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Labels (Gmail-style flexible categorization)
    labels TEXT[] DEFAULT '{}',                  -- e.g., ['urgent', 'build', 'follow-up']

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ                       -- Optional TTL (no default)
);

-- Indexes for agent_messages
CREATE INDEX IF NOT EXISTS idx_agent_messages_to ON argus.agent_messages(to_agent, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_messages_from ON argus.agent_messages(from_agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_messages_thread ON argus.agent_messages(thread_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_messages_status ON argus.agent_messages(status) WHERE status IN ('pending', 'read', 'in_progress');
CREATE INDEX IF NOT EXISTS idx_agent_messages_priority ON argus.agent_messages(priority, created_at DESC) WHERE priority IN ('critical', 'high');
CREATE INDEX IF NOT EXISTS idx_agent_messages_search ON argus.agent_messages USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_agent_messages_project ON argus.agent_messages(related_project, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_messages_type ON argus.agent_messages(message_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_messages_labels ON argus.agent_messages USING GIN(labels);

-- ============================================================================
-- MESSAGE READ RECEIPTS (for broadcasts/cc)
-- ============================================================================

CREATE TABLE IF NOT EXISTS argus.agent_message_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES argus.agent_messages(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES argus.agents(id),

    status TEXT DEFAULT 'delivered',             -- delivered, read, actioned
    read_at TIMESTAMPTZ,
    actioned_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(message_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_message_receipts_agent ON argus.agent_message_receipts(agent_id, status);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Inbox view (unread/pending messages for an agent)
CREATE OR REPLACE VIEW argus.v_agent_inbox AS
SELECT
    m.*,
    a_from.name as from_agent_name,
    a_to.name as to_agent_name
FROM argus.agent_messages m
LEFT JOIN argus.agents a_from ON m.from_agent = a_from.id
LEFT JOIN argus.agents a_to ON m.to_agent = a_to.id
WHERE m.status IN ('pending', 'read', 'in_progress')
ORDER BY
    CASE m.priority
        WHEN 'critical' THEN 0
        WHEN 'high' THEN 1
        WHEN 'normal' THEN 2
        ELSE 3
    END,
    m.created_at DESC;

-- Thread view (messages grouped by thread)
CREATE OR REPLACE VIEW argus.v_agent_threads AS
SELECT
    thread_id,
    thread_subject,
    MIN(created_at) as thread_started,
    MAX(created_at) as last_message_at,
    COUNT(*) as message_count,
    ARRAY_AGG(DISTINCT from_agent) as participants,
    MAX(CASE WHEN status IN ('pending', 'in_progress') THEN 1 ELSE 0 END) > 0 as has_pending
FROM argus.agent_messages
WHERE thread_id IS NOT NULL
GROUP BY thread_id, thread_subject
ORDER BY last_message_at DESC;

-- Recent activity across all agents
CREATE OR REPLACE VIEW argus.v_agent_message_activity AS
SELECT
    DATE_TRUNC('hour', created_at) as hour,
    from_agent,
    to_agent,
    message_type,
    COUNT(*) as message_count
FROM argus.agent_messages
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Send a message (convenience function)
CREATE OR REPLACE FUNCTION argus.send_agent_message(
    p_from_agent TEXT,
    p_to_agent TEXT,
    p_subject TEXT,
    p_body TEXT,
    p_message_type TEXT DEFAULT 'notification',
    p_priority TEXT DEFAULT 'normal',
    p_thread_id TEXT DEFAULT NULL,
    p_reply_to_id UUID DEFAULT NULL,
    p_action_requested TEXT DEFAULT NULL,
    p_related_project TEXT DEFAULT NULL,
    p_related_component TEXT DEFAULT NULL,
    p_labels TEXT[] DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_message_id UUID;
    v_thread_id TEXT;
    v_thread_subject TEXT;
BEGIN
    -- Handle threading
    IF p_reply_to_id IS NOT NULL THEN
        SELECT thread_id, COALESCE(thread_subject, subject)
        INTO v_thread_id, v_thread_subject
        FROM argus.agent_messages WHERE id = p_reply_to_id;
    ELSE
        v_thread_id := COALESCE(p_thread_id, 'thread_' || gen_random_uuid()::text);
        v_thread_subject := p_subject;
    END IF;

    INSERT INTO argus.agent_messages (
        from_agent, to_agent, subject, body, message_type, priority,
        thread_id, thread_subject, reply_to_id, action_requested,
        related_project, related_component, labels
    ) VALUES (
        p_from_agent, p_to_agent, p_subject, p_body, p_message_type, p_priority,
        v_thread_id, v_thread_subject, p_reply_to_id, p_action_requested,
        p_related_project, p_related_component, p_labels
    ) RETURNING id INTO v_message_id;

    RETURN v_message_id;
END;
$$ LANGUAGE plpgsql;

-- Get inbox for an agent
CREATE OR REPLACE FUNCTION argus.get_agent_inbox(
    p_agent_id TEXT,
    p_status TEXT[] DEFAULT ARRAY['pending', 'read', 'in_progress'],
    p_limit INTEGER DEFAULT 50
) RETURNS TABLE (
    id UUID,
    message_id TEXT,
    from_agent TEXT,
    from_agent_name TEXT,
    subject TEXT,
    body TEXT,
    message_type TEXT,
    priority TEXT,
    status TEXT,
    thread_id TEXT,
    labels TEXT[],
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id, m.message_id, m.from_agent, a.name,
        m.subject, m.body, m.message_type, m.priority,
        m.status, m.thread_id, m.labels, m.created_at
    FROM argus.agent_messages m
    LEFT JOIN argus.agents a ON m.from_agent = a.id
    WHERE (m.to_agent = p_agent_id OR m.to_agent IS NULL)  -- Include broadcasts
      AND m.status = ANY(p_status)
    ORDER BY
        CASE m.priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,
        m.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Mark message as read/actioned
CREATE OR REPLACE FUNCTION argus.update_message_status(
    p_message_id UUID,
    p_status TEXT,
    p_agent_id TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    UPDATE argus.agent_messages
    SET
        status = p_status,
        read_at = CASE WHEN p_status IN ('read', 'in_progress', 'completed') AND read_at IS NULL
                       THEN NOW() ELSE read_at END,
        actioned_at = CASE WHEN p_status = 'in_progress' AND actioned_at IS NULL
                           THEN NOW() ELSE actioned_at END,
        completed_at = CASE WHEN p_status IN ('completed', 'failed')
                            THEN NOW() ELSE completed_at END,
        updated_at = NOW()
    WHERE id = p_message_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- REGISTER INITIAL AGENTS
-- ============================================================================

-- Mac client agent
INSERT INTO argus.agents (id, name, description, category, is_active)
VALUES ('mac-client', 'Mac Client', 'Client-side daemon on MacBook for syncing local data', 'sync', true)
ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    updated_at = NOW();

-- Rhea server agent
INSERT INTO argus.agents (id, name, description, category, is_active)
VALUES ('rhea-server', 'Rhea Server', 'Server-side agent for ETL, builds, and processing', 'etl', true)
ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    updated_at = NOW();

-- Rhea builder agent (Claude on server)
INSERT INTO argus.agents (id, name, description, category, is_active)
VALUES ('rhea-builder', 'Rhea Builder', 'Server-side Claude for building software from specs', 'build', true)
ON CONFLICT (id) DO UPDATE SET
    description = EXCLUDED.description,
    updated_at = NOW();

-- ============================================================================
-- DONE
-- ============================================================================

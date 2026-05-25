-- Authenticated send function
CREATE OR REPLACE FUNCTION argus.send_agent_message_auth(
    p_api_key TEXT,
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
BEGIN
    IF NOT argus.verify_agent(p_from_agent, p_api_key) THEN
        RAISE EXCEPTION 'Authentication failed for agent: %', p_from_agent;
    END IF;
    RETURN argus.send_agent_message(
        p_from_agent, p_to_agent, p_subject, p_body,
        p_message_type, p_priority, p_thread_id, p_reply_to_id,
        p_action_requested, p_related_project, p_related_component, p_labels
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Authenticated inbox function
CREATE OR REPLACE FUNCTION argus.get_agent_inbox_auth(
    p_api_key TEXT,
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
    IF NOT argus.verify_agent(p_agent_id, p_api_key) THEN
        RAISE EXCEPTION 'Authentication failed for agent: %', p_agent_id;
    END IF;
    RETURN QUERY SELECT * FROM argus.get_agent_inbox(p_agent_id, p_status, p_limit);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Authenticated status update
CREATE OR REPLACE FUNCTION argus.update_message_status_auth(
    p_api_key TEXT,
    p_agent_id TEXT,
    p_message_id UUID,
    p_status TEXT
) RETURNS VOID AS $$
BEGIN
    IF NOT argus.verify_agent(p_agent_id, p_api_key) THEN
        RAISE EXCEPTION 'Authentication failed for agent: %', p_agent_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM argus.agent_messages
        WHERE id = p_message_id
        AND (to_agent = p_agent_id OR from_agent = p_agent_id OR to_agent IS NULL)
    ) THEN
        RAISE EXCEPTION 'Agent % does not have access to message %', p_agent_id, p_message_id;
    END IF;

    PERFORM argus.update_message_status(p_message_id, p_status, p_agent_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

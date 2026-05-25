#!/usr/bin/env python3
"""
Agent Watcher Daemon

Polls argus.agent_messages for pending messages addressed to this agent.
When messages are found, spawns Claude Code to handle them.

This is the heartbeat that maintains AI agency across sessions.
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path

import psycopg2
from sshtunnel import SSHTunnelForwarder

# Configuration
AGENT_ID = os.getenv("AGENT_ID", "mac-client")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "ak_PjI82IPXFb3o3K8R6yd4ntT63xwSXjec")

# SSH tunnel to rhea-dev
SSH_HOST = os.getenv("SSH_HOST", "rhea-dev")
SSH_USER = os.getenv("SSH_USER", "dshanklin")
SSH_KEY = os.getenv("SSH_KEY", str(Path.home() / ".ssh" / "id_ed25519"))

# Postgres on rhea-dev (via docker network)
PG_HOST = os.getenv("PG_HOST", "10.0.1.5")  # Coolify postgres internal IP
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DATABASE = os.getenv("PG_DATABASE", "argus")
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "TITDfWcaSgxWupqj3VEpBT83YtXbaAtrC1R4pXFKG0L2WbrfBo7myPjliwfsYOVi")

# Logging
LOG_DIR = Path.home() / "Library" / "Logs" / "mac-bridge"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "agent-watcher.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Create SSH tunnel and return database connection."""
    tunnel = SSHTunnelForwarder(
        SSH_HOST,
        ssh_username=SSH_USER,
        ssh_pkey=SSH_KEY,
        remote_bind_address=(PG_HOST, PG_PORT),
        local_bind_address=('localhost', 0),  # Random local port
    )
    tunnel.start()

    conn = psycopg2.connect(
        host='localhost',
        port=tunnel.local_bind_port,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD,
    )

    return conn, tunnel


def check_inbox(conn) -> list:
    """Check for pending messages addressed to this agent."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, from_agent, subject, priority, message_type, body
            FROM argus.agent_messages
            WHERE to_agent = %s
              AND status IN ('pending', 'in_progress')
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at ASC
            LIMIT 10
        """, (AGENT_ID,))

        columns = [desc[0] for desc in cur.description]
        messages = [dict(zip(columns, row)) for row in cur.fetchall()]

    return messages


def start_session(conn, trigger_type: str, trigger_message_id: str = None) -> str:
    """Record session start in agent_sessions table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT argus.start_agent_session(%s, %s, %s)
        """, (AGENT_ID, trigger_type, trigger_message_id))
        session_id = cur.fetchone()[0]
        conn.commit()

    return str(session_id)


def end_session(conn, session_id: str, outcome: str, messages_read: int,
                messages_sent: int, summary: str = None, error: str = None):
    """Record session end in agent_sessions table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT argus.end_agent_session(%s, %s, %s, %s, %s, %s, NULL, NULL)
        """, (session_id, outcome, messages_read, messages_sent, summary, error))
        conn.commit()


def spawn_claude(messages: list, session_id: str) -> dict:
    """Spawn Claude Code to handle the messages."""

    # Build prompt with inbox context
    message_summary = "\n".join([
        f"- [{m['priority'].upper()}] From {m['from_agent']}: {m['subject']}"
        for m in messages
    ])

    prompt = f"""You have {len(messages)} pending messages in your inbox.

## Messages:
{message_summary}

## Instructions:
1. Read your full inbox using the agent messaging system
2. Process messages by priority (critical > high > normal > low)
3. Take appropriate action for each message
4. Send responses as needed
5. Mark messages as completed when done

Your agent ID is: {AGENT_ID}
Your API key is: {AGENT_API_KEY}
Session ID for logging: {session_id}

When you're done, summarize what you accomplished.
"""

    logger.info(f"Spawning Claude with {len(messages)} messages to process")

    try:
        # Run claude code with the prompt
        result = subprocess.run(
            ["claude", "--print", "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(Path.home() / "repos-personal" / "mac-bridge")
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }

    except subprocess.TimeoutExpired:
        logger.error("Claude session timed out after 10 minutes")
        return {
            "success": False,
            "error": "timeout",
            "stdout": "",
            "stderr": "Session timed out after 10 minutes"
        }
    except Exception as e:
        logger.error(f"Error spawning Claude: {e}")
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "stderr": str(e)
        }


def main():
    """Main watcher loop (single check)."""
    logger.info(f"Agent watcher starting for {AGENT_ID}")

    conn = None
    tunnel = None
    session_id = None

    try:
        # Connect to database
        conn, tunnel = get_db_connection()
        logger.info("Connected to argus database")

        # Check inbox
        messages = check_inbox(conn)

        if not messages:
            logger.info("No pending messages")
            return 0

        logger.info(f"Found {len(messages)} pending message(s)")

        # Start session (use first message as trigger)
        first_msg_id = str(messages[0]['id'])
        session_id = start_session(conn, 'cron', first_msg_id)
        logger.info(f"Started session {session_id}")

        # Spawn Claude to handle messages
        result = spawn_claude(messages, session_id)

        # End session
        outcome = 'completed' if result['success'] else 'error'
        summary = result['stdout'][:500] if result['stdout'] else None
        error = result['stderr'][:500] if not result['success'] and result['stderr'] else None

        end_session(
            conn,
            session_id,
            outcome=outcome,
            messages_read=len(messages),
            messages_sent=0,  # Would need to count from Claude output
            summary=summary,
            error=error
        )

        logger.info(f"Session {session_id} ended with outcome: {outcome}")

        return 0 if result['success'] else 1

    except Exception as e:
        logger.error(f"Watcher error: {e}")

        # Try to end session with error if we have one
        if session_id and conn:
            try:
                end_session(conn, session_id, 'error', 0, 0, error=str(e))
            except:
                pass

        return 1

    finally:
        if conn:
            conn.close()
        if tunnel:
            tunnel.stop()


if __name__ == "__main__":
    sys.exit(main())

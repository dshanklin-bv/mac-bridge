"""
tosh check-inbox - Check for pending assignments from reeves.

Usage:
    python -m tosh.cli.inbox
"""

import logging
import sys
import subprocess
from typing import Optional, Dict, Any

from tosh.utils.db import get_argus_connection, DatabaseError
from tosh.utils.config import get

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _get_agent_id() -> str:
    """Get agent ID from config."""
    return get("agent.id", "tosh")


def _get_api_key() -> str:
    """Get agent API key from config."""
    key = get("agent.api_key")
    if not key:
        raise ValueError("agent.api_key not set in config")
    return key


def get_pending_assignments() -> list:
    """
    Get pending assignment messages from inbox.

    Returns:
        List of pending assignment messages.
    """
    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, from_agent, subject, body, priority, created_at
                FROM argus.agent_messages
                WHERE to_agent = %s
                  AND status = 'pending'
                  AND message_type = 'assignment'
                ORDER BY priority DESC, created_at ASC
                LIMIT 10
            """, (_get_agent_id(),))

            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    except DatabaseError as e:
        logger.error(f"Failed to check inbox: {e}")
        return []
    finally:
        conn.close()


def mark_in_progress(message_id: str) -> bool:
    """Mark a message as in_progress."""
    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT argus.update_message_status_auth(%s, %s, %s, 'in_progress')
            """, (_get_api_key(), _get_agent_id(), message_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to mark message in_progress: {e}")
        return False
    finally:
        conn.close()


def spawn_claude_session(message: Dict[str, Any]) -> int:
    """
    Spawn a Claude session to handle an assignment.

    Args:
        message: The assignment message dict.

    Returns:
        Exit code from Claude session.
    """
    subject = message.get('subject', 'Assignment')
    body = message.get('body', '')
    message_id = str(message.get('id', ''))
    agent_id = _get_agent_id()
    api_key = _get_api_key()

    prompt = f"""You are tosh, the Mac-side data agent.

You have received an assignment from reeves:

Subject: {subject}

{body}

---

Complete this assignment and send a response message to reeves when done.
Use the agent messaging system in argus database.

Your API key: {api_key}
Your agent ID: {agent_id}
Message ID to reply to: {message_id}
"""

    logger.info(f"Spawning Claude session for: {subject}")

    # Write prompt to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        # Spawn Claude CLI
        result = subprocess.run(
            ['claude', '--print', '-p', prompt_file],
            capture_output=False,
            timeout=300  # 5 minute timeout
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.error("Claude session timed out")
        return 1
    except FileNotFoundError:
        logger.error("Claude CLI not found")
        return 1
    finally:
        import os
        os.unlink(prompt_file)


def main():
    logger.info("Checking inbox for assignments...")

    assignments = get_pending_assignments()

    if not assignments:
        logger.info("No pending assignments")
        return 0

    logger.info(f"Found {len(assignments)} pending assignment(s)")

    for msg in assignments:
        subject = msg.get('subject', 'Unknown')
        logger.info(f"Processing: {subject}")

        # Mark as in_progress
        if mark_in_progress(str(msg['id'])):
            # Spawn Claude to handle it
            exit_code = spawn_claude_session(msg)
            if exit_code != 0:
                logger.warning(f"Claude session exited with code {exit_code}")
        else:
            logger.warning(f"Could not mark message in_progress, skipping")

    return 0


if __name__ == '__main__':
    sys.exit(main())

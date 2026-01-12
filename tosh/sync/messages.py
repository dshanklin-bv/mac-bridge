"""
Sync iMessage/SMS messages to bronze.apple_messages.
Reads from ~/Library/Messages/chat.db
Uses watermarks for incremental sync.
"""

import sqlite3
import logging
from pathlib import Path
from typing import List, Tuple, Any, Optional

from psycopg2.extras import execute_values

from tosh.utils.db import get_connection
from tosh.utils.watermark import get_watermark, set_watermark

logger = logging.getLogger(__name__)

WATERMARK_COLUMN = "date"  # Apple epoch nanoseconds

MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"
BATCH_SIZE = 2000


def get_local_db() -> sqlite3.Connection:
    """Get connection to local Messages database."""
    if not MESSAGES_DB.exists():
        raise FileNotFoundError(f"Messages database not found: {MESSAGES_DB}")

    conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _batch_upsert(cur, table: str, columns: List[str], values: List[Tuple],
                  conflict_col: str, update_cols: List[str]) -> int:
    """
    Batch upsert using execute_values.

    Args:
        cur: Database cursor
        table: Target table name
        columns: Column names
        values: List of value tuples
        conflict_col: Column for ON CONFLICT
        update_cols: Columns to update on conflict

    Returns:
        Number of rows affected
    """
    if not values:
        return 0

    col_list = ", ".join(columns)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
    update_set += ", synced_at = NOW()"

    sql = f"""
        INSERT INTO {table} ({col_list})
        VALUES %s
        ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}
    """

    execute_values(cur, sql, values, page_size=BATCH_SIZE)
    return len(values)


def sync() -> int:
    """
    Sync messages to bronze layer using batch inserts with watermarks.

    Returns:
        Number of records synced.
    """
    # Get current watermark for incremental sync
    watermark = get_watermark("messages")
    if watermark:
        logger.info(f"Using watermark: {WATERMARK_COLUMN} > {watermark}")
    else:
        logger.info("No watermark found, doing full sync")

    logger.info("Reading local Messages database...")

    local_conn = get_local_db()

    try:
        local_cur = local_conn.cursor()

        # Get handles (always full sync - small table)
        local_cur.execute("""
            SELECT ROWID as rowid, id as identifier, service
            FROM handle
        """)
        handles = [(row['rowid'], row['identifier'], row['service'])
                   for row in local_cur.fetchall()]
        logger.info(f"Found {len(handles)} handles locally")

        # Get chats (always full sync - small table)
        local_cur.execute("""
            SELECT ROWID as rowid, guid, chat_identifier, display_name, service_name
            FROM chat
        """)
        chats = [(row['rowid'], row['guid'], row['chat_identifier'],
                  row['display_name'], row['service_name'])
                 for row in local_cur.fetchall()]
        logger.info(f"Found {len(chats)} chats locally")

        # Get chat-message associations (need all for FK resolution)
        local_cur.execute("""
            SELECT chat_id, message_id FROM chat_message_join
        """)
        chat_messages = {row['message_id']: row['chat_id']
                        for row in local_cur.fetchall()}

        # Get messages (incremental if watermark exists)
        if watermark:
            local_cur.execute("""
                SELECT
                    ROWID as rowid,
                    guid,
                    text,
                    handle_id,
                    date as date_apple,
                    date_read as date_read_apple,
                    date_delivered as date_delivered_apple,
                    is_from_me,
                    service,
                    cache_has_attachments,
                    thread_originator_guid
                FROM message
                WHERE guid IS NOT NULL AND date > ?
                ORDER BY date ASC
            """, (int(watermark),))
        else:
            local_cur.execute("""
                SELECT
                    ROWID as rowid,
                    guid,
                    text,
                    handle_id,
                    date as date_apple,
                    date_read as date_read_apple,
                    date_delivered as date_delivered_apple,
                    is_from_me,
                    service,
                    cache_has_attachments,
                    thread_originator_guid
                FROM message
                WHERE guid IS NOT NULL
                ORDER BY date ASC
            """)

        messages = []
        max_date = None
        for row in local_cur.fetchall():
            chat_id = chat_messages.get(row['rowid'])
            messages.append((
                row['rowid'], row['guid'], row['text'], row['handle_id'], chat_id,
                row['date_apple'], row['date_read_apple'], row['date_delivered_apple'],
                bool(row['is_from_me']), row['service'], bool(row['cache_has_attachments']),
                row['thread_originator_guid']
            ))
            # Track max date for watermark
            if row['date_apple'] and (max_date is None or row['date_apple'] > max_date):
                max_date = row['date_apple']

        logger.info(f"Found {len(messages)} messages to sync")

        local_conn.close()

        # Sync to bronze in single transaction with batch inserts
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Sync handles
                logger.info("Syncing handles...")
                _batch_upsert(
                    cur, "bronze.apple_handles",
                    ["mac_rowid", "identifier", "service"],
                    handles,
                    "mac_rowid",
                    ["identifier", "service"]
                )

                # Sync chats
                logger.info("Syncing chats...")
                _batch_upsert(
                    cur, "bronze.apple_chats",
                    ["mac_rowid", "guid", "chat_identifier", "display_name", "service_name"],
                    chats,
                    "mac_rowid",
                    ["guid", "chat_identifier", "display_name", "service_name"]
                )

                # Sync messages
                logger.info("Syncing messages...")
                _batch_upsert(
                    cur, "bronze.apple_messages",
                    ["mac_rowid", "guid", "text", "handle_id", "chat_id",
                     "date_apple", "date_read_apple", "date_delivered_apple",
                     "is_from_me", "service", "cache_has_attachments", "thread_originator_guid"],
                    messages,
                    "mac_rowid",
                    ["text", "date_read_apple", "date_delivered_apple"]
                )

            conn.commit()
            logger.info(f"Synced {len(messages)} messages to bronze")

            # Update watermark AFTER successful commit
            if max_date is not None:
                set_watermark("messages", WATERMARK_COLUMN, str(max_date), len(messages))

            return len(messages)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Messages sync failed: {e}")
        raise

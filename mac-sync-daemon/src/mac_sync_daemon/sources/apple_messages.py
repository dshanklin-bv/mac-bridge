"""Sync Apple Messages (iMessage/SMS) from chat.db to bronze layer."""

import sqlite3
import logging
from pathlib import Path

from .. import config
from ..db import get_db

logger = logging.getLogger(__name__)


def get_sqlite_connection():
    """Open read-only connection to chat.db."""
    db_path = config.MESSAGES_DB
    if not db_path.exists():
        raise FileNotFoundError(f"Messages database not found: {db_path}")

    # Open in read-only mode
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_last_synced_id(source_name: str) -> int:
    """Get the last synced ROWID for a source."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT last_sync_id FROM sync.sources WHERE name = %s",
            (source_name,)
        )
        row = cur.fetchone()
        return row[0] if row else 0


def update_sync_state(source_name: str, last_id: int, count: int):
    """Update sync state after successful sync."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            UPDATE sync.sources
            SET last_sync_id = %s,
                last_sync_count = %s,
                last_sync_at = NOW(),
                sync_status = 'success',
                sync_error = NULL,
                updated_at = NOW()
            WHERE name = %s
        """, (last_id, count, source_name))


def sync_handles() -> int:
    """Sync handles (phone numbers/emails) to bronze layer."""
    logger.info("Syncing handles...")

    last_id = get_last_synced_id('apple_handles')
    sqlite_conn = get_sqlite_connection()
    db = get_db()

    try:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute("""
            SELECT ROWID, id, service, country, person_centric_id
            FROM handle
            WHERE ROWID > ?
            ORDER BY ROWID
            LIMIT ?
        """, (last_id, config.BATCH_SIZE))

        rows = sqlite_cur.fetchall()
        if not rows:
            logger.info("No new handles to sync")
            return 0

        max_rowid = last_id
        count = 0

        with db.cursor() as pg_cur:
            for row in rows:
                pg_cur.execute("""
                    INSERT INTO bronze.apple_handles
                        (mac_rowid, identifier, service, country, person_centric_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (mac_rowid) DO UPDATE SET
                        identifier = EXCLUDED.identifier,
                        service = EXCLUDED.service,
                        synced_at = NOW()
                """, (row['ROWID'], row['id'], row['service'],
                      row['country'], row['person_centric_id']))
                max_rowid = max(max_rowid, row['ROWID'])
                count += 1

        # Update sync state (use a different source name for handles)
        with db.cursor() as pg_cur:
            pg_cur.execute("""
                INSERT INTO sync.sources (name, display_name, last_sync_id, last_sync_count, last_sync_at, sync_status)
                VALUES ('apple_handles', 'Apple Handles', %s, %s, NOW(), 'success')
                ON CONFLICT (name) DO UPDATE SET
                    last_sync_id = EXCLUDED.last_sync_id,
                    last_sync_count = EXCLUDED.last_sync_count,
                    last_sync_at = NOW(),
                    sync_status = 'success'
            """, (max_rowid, count))

        logger.info(f"Synced {count} handles (up to ROWID {max_rowid})")
        return count

    finally:
        sqlite_conn.close()


def sync_chats() -> int:
    """Sync chats (conversations) to bronze layer."""
    logger.info("Syncing chats...")

    last_id = get_last_synced_id('apple_chats')
    sqlite_conn = get_sqlite_connection()
    db = get_db()

    try:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute("""
            SELECT ROWID, guid, chat_identifier, service_name,
                   display_name, is_archived
            FROM chat
            WHERE ROWID > ?
            ORDER BY ROWID
            LIMIT ?
        """, (last_id, config.BATCH_SIZE))

        rows = sqlite_cur.fetchall()
        if not rows:
            logger.info("No new chats to sync")
            return 0

        max_rowid = last_id
        count = 0

        with db.cursor() as pg_cur:
            for row in rows:
                pg_cur.execute("""
                    INSERT INTO bronze.apple_chats
                        (mac_rowid, guid, chat_identifier, service_name,
                         display_name, is_archived)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mac_rowid) DO UPDATE SET
                        guid = EXCLUDED.guid,
                        chat_identifier = EXCLUDED.chat_identifier,
                        display_name = EXCLUDED.display_name,
                        synced_at = NOW()
                """, (row['ROWID'], row['guid'], row['chat_identifier'],
                      row['service_name'], row['display_name'],
                      bool(row['is_archived'])))
                max_rowid = max(max_rowid, row['ROWID'])
                count += 1

        with db.cursor() as pg_cur:
            pg_cur.execute("""
                INSERT INTO sync.sources (name, display_name, last_sync_id, last_sync_count, last_sync_at, sync_status)
                VALUES ('apple_chats', 'Apple Chats', %s, %s, NOW(), 'success')
                ON CONFLICT (name) DO UPDATE SET
                    last_sync_id = EXCLUDED.last_sync_id,
                    last_sync_count = EXCLUDED.last_sync_count,
                    last_sync_at = NOW(),
                    sync_status = 'success'
            """, (max_rowid, count))

        logger.info(f"Synced {count} chats (up to ROWID {max_rowid})")
        return count

    finally:
        sqlite_conn.close()


def sync_messages() -> int:
    """Sync messages to bronze layer."""
    logger.info("Syncing messages...")

    last_id = get_last_synced_id('apple_messages')
    sqlite_conn = get_sqlite_connection()
    db = get_db()

    try:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute("""
            SELECT m.ROWID, m.guid, m.text, m.handle_id,
                   cmj.chat_id,
                   m.date, m.date_read, m.date_delivered,
                   m.is_from_me, m.is_read, m.is_delivered, m.is_sent,
                   m.service, m.thread_originator_guid,
                   m.associated_message_guid, m.cache_has_attachments
            FROM message m
            LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            WHERE m.ROWID > ?
            ORDER BY m.ROWID
            LIMIT ?
        """, (last_id, config.BATCH_SIZE))

        rows = sqlite_cur.fetchall()
        if not rows:
            logger.info("No new messages to sync")
            return 0

        max_rowid = last_id
        count = 0

        with db.cursor() as pg_cur:
            for row in rows:
                pg_cur.execute("""
                    INSERT INTO bronze.apple_messages
                        (mac_rowid, guid, text, handle_id, chat_id,
                         date_apple, date_read_apple, date_delivered_apple,
                         is_from_me, is_read, is_delivered, is_sent,
                         service, thread_originator_guid,
                         associated_message_guid, cache_has_attachments)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mac_rowid) DO UPDATE SET
                        text = EXCLUDED.text,
                        is_read = EXCLUDED.is_read,
                        date_read_apple = EXCLUDED.date_read_apple,
                        synced_at = NOW()
                """, (
                    row['ROWID'], row['guid'], row['text'], row['handle_id'],
                    row['chat_id'], row['date'], row['date_read'],
                    row['date_delivered'], bool(row['is_from_me']),
                    bool(row['is_read']), bool(row['is_delivered']),
                    bool(row['is_sent']), row['service'],
                    row['thread_originator_guid'], row['associated_message_guid'],
                    bool(row['cache_has_attachments'])
                ))
                max_rowid = max(max_rowid, row['ROWID'])
                count += 1

        update_sync_state('apple_messages', max_rowid, count)

        logger.info(f"Synced {count} messages (up to ROWID {max_rowid})")
        return count

    finally:
        sqlite_conn.close()

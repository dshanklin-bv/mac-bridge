"""Sync Apple Call History to bronze layer."""

import sqlite3
import logging
from pathlib import Path

from .. import config
from ..db import get_db

logger = logging.getLogger(__name__)


def get_sqlite_connection():
    """Open read-only connection to CallHistory.storedata."""
    db_path = config.CALLS_DB
    if not db_path.exists():
        raise FileNotFoundError(f"Call history database not found: {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_last_synced_id() -> int:
    """Get the last synced Z_PK."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT last_sync_id FROM sync.sources WHERE name = 'apple_calls'"
        )
        row = cur.fetchone()
        return row[0] if row else 0


def sync_calls() -> int:
    """Sync calls to bronze layer."""
    logger.info("Syncing calls...")

    last_id = get_last_synced_id()
    sqlite_conn = get_sqlite_connection()
    db = get_db()

    try:
        sqlite_cur = sqlite_conn.cursor()
        sqlite_cur.execute("""
            SELECT Z_PK, ZUNIQUE_ID, ZDATE, ZDURATION,
                   ZADDRESS, ZNAME, ZORIGINATED, ZANSWERED,
                   ZCALLTYPE, ZSERVICE_PROVIDER
            FROM ZCALLRECORD
            WHERE Z_PK > ?
            ORDER BY Z_PK
            LIMIT ?
        """, (last_id, config.BATCH_SIZE))

        rows = sqlite_cur.fetchall()
        if not rows:
            logger.info("No new calls to sync")
            return 0

        max_pk = last_id
        count = 0

        with db.cursor() as pg_cur:
            for row in rows:
                pg_cur.execute("""
                    INSERT INTO bronze.apple_calls
                        (mac_pk, unique_id, date_apple, duration_seconds,
                         address, name, is_outgoing, is_answered,
                         call_type, service_provider)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mac_pk) DO UPDATE SET
                        unique_id = EXCLUDED.unique_id,
                        address = EXCLUDED.address,
                        name = EXCLUDED.name,
                        synced_at = NOW()
                """, (
                    row['Z_PK'], row['ZUNIQUE_ID'], row['ZDATE'],
                    row['ZDURATION'], row['ZADDRESS'], row['ZNAME'],
                    bool(row['ZORIGINATED']), bool(row['ZANSWERED']),
                    row['ZCALLTYPE'], row['ZSERVICE_PROVIDER']
                ))
                max_pk = max(max_pk, row['Z_PK'])
                count += 1

        # Update sync state
        with db.cursor() as pg_cur:
            pg_cur.execute("""
                UPDATE sync.sources
                SET last_sync_id = %s,
                    last_sync_count = %s,
                    last_sync_at = NOW(),
                    sync_status = 'success',
                    sync_error = NULL,
                    updated_at = NOW()
                WHERE name = 'apple_calls'
            """, (max_pk, count))

        logger.info(f"Synced {count} calls (up to Z_PK {max_pk})")
        return count

    finally:
        sqlite_conn.close()

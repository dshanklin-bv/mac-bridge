"""
Sync call history to bronze.apple_calls.
Reads from ~/Library/Application Support/CallHistoryDB/CallHistory.storedata
Uses watermarks for incremental sync.
"""

import sqlite3
import logging
from pathlib import Path

from psycopg2.extras import execute_values

from tosh.utils.db import get_connection
from tosh.utils.watermark import get_watermark, set_watermark

logger = logging.getLogger(__name__)

WATERMARK_COLUMN = "ZDATE"  # Apple epoch seconds

CALLS_DB = Path.home() / "Library" / "Application Support" / "CallHistoryDB" / "CallHistory.storedata"
BATCH_SIZE = 2000


def get_local_db() -> sqlite3.Connection:
    """Get connection to local CallHistory database."""
    if not CALLS_DB.exists():
        raise FileNotFoundError(f"CallHistory database not found: {CALLS_DB}")

    conn = sqlite3.connect(f"file:{CALLS_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sync() -> int:
    """
    Sync call history to bronze layer using batch inserts with watermarks.

    Returns:
        Number of records synced.
    """
    # Get current watermark for incremental sync
    watermark = get_watermark("calls")
    if watermark:
        logger.info(f"Using watermark: {WATERMARK_COLUMN} > {watermark}")
    else:
        logger.info("No watermark found, doing full sync")

    logger.info("Reading local CallHistory database...")

    local_conn = get_local_db()

    try:
        local_cur = local_conn.cursor()

        if watermark:
            local_cur.execute("""
                SELECT
                    Z_PK as rowid,
                    ZUNIQUE_ID as unique_id,
                    ZADDRESS as address,
                    ZNAME as name,
                    ZDATE as date_apple,
                    ZDURATION as duration,
                    ZORIGINATED as is_outgoing,
                    ZANSWERED as is_answered,
                    ZCALLTYPE as call_type,
                    ZSERVICE_PROVIDER as service_provider
                FROM ZCALLRECORD
                WHERE ZUNIQUE_ID IS NOT NULL AND ZDATE > ?
                ORDER BY ZDATE ASC
            """, (float(watermark),))
        else:
            local_cur.execute("""
                SELECT
                    Z_PK as rowid,
                    ZUNIQUE_ID as unique_id,
                    ZADDRESS as address,
                    ZNAME as name,
                    ZDATE as date_apple,
                    ZDURATION as duration,
                    ZORIGINATED as is_outgoing,
                    ZANSWERED as is_answered,
                    ZCALLTYPE as call_type,
                    ZSERVICE_PROVIDER as service_provider
                FROM ZCALLRECORD
                WHERE ZUNIQUE_ID IS NOT NULL
                ORDER BY ZDATE ASC
            """)

        calls = []
        max_date = None
        for row in local_cur.fetchall():
            calls.append((
                row['rowid'], row['unique_id'], row['date_apple'], row['duration'],
                row['address'], row['name'],
                bool(row['is_outgoing']), bool(row['is_answered']), row['call_type'],
                row['service_provider']
            ))
            # Track max date for watermark
            if row['date_apple'] and (max_date is None or row['date_apple'] > max_date):
                max_date = row['date_apple']

        logger.info(f"Found {len(calls)} calls to sync")
        local_conn.close()

        if not calls:
            return 0

        # Sync to bronze with batch insert
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                sql = """
                    INSERT INTO bronze.apple_calls (
                        mac_pk, unique_id, date_apple, duration_seconds,
                        address, name, is_outgoing, is_answered, call_type, service_provider
                    )
                    VALUES %s
                    ON CONFLICT (mac_pk) DO UPDATE SET
                        name = EXCLUDED.name,
                        synced_at = NOW()
                """
                execute_values(cur, sql, calls, page_size=BATCH_SIZE)

            conn.commit()
            logger.info(f"Synced {len(calls)} calls to bronze")

            # Update watermark AFTER successful commit
            if max_date is not None:
                set_watermark("calls", WATERMARK_COLUMN, str(max_date), len(calls))

            return len(calls)

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Calls sync failed: {e}")
        raise

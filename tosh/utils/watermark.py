"""
Watermark management for incremental sync.
Stores/retrieves watermarks from argus.sync_watermarks.
"""

from datetime import datetime, timezone
from typing import Optional

from tosh.utils.db import get_argus_connection
from tosh.utils.logging import get_logger

logger = get_logger(__name__)

DEVICE_SOURCE = "tosh-mac"


def get_watermark(sync_type: str) -> Optional[str]:
    """
    Get the current watermark for a sync type.

    Args:
        sync_type: Type of sync (messages, calls, contacts)

    Returns:
        Watermark value as string, or None if not set
    """
    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT watermark_value
                FROM argus.sync_watermarks
                WHERE source = %s AND sync_type = %s
            """, (DEVICE_SOURCE, sync_type))

            row = cur.fetchone()
            if row:
                return row[0]
            return None
    except Exception as e:
        logger.error(f"Failed to get watermark for {sync_type}: {e}")
        return None
    finally:
        conn.close()


def set_watermark(
    sync_type: str,
    watermark_column: str,
    watermark_value: str,
    rows_synced: int
) -> bool:
    """
    Set the watermark for a sync type.

    Args:
        sync_type: Type of sync (messages, calls, contacts)
        watermark_column: Column name used as watermark
        watermark_value: New watermark value
        rows_synced: Number of rows synced in this run

    Returns:
        True if successful
    """
    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO argus.sync_watermarks (
                    source, sync_type, watermark_column, watermark_value,
                    rows_synced, last_sync_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (source, sync_type) DO UPDATE SET
                    watermark_column = EXCLUDED.watermark_column,
                    watermark_value = EXCLUDED.watermark_value,
                    rows_synced = EXCLUDED.rows_synced,
                    last_sync_at = NOW(),
                    updated_at = NOW()
            """, (DEVICE_SOURCE, sync_type, watermark_column, watermark_value, rows_synced))

        conn.commit()
        logger.info(
            f"Watermark updated",
            sync_type=sync_type,
            watermark_column=watermark_column,
            watermark_value=watermark_value,
            rows_synced=rows_synced
        )
        return True
    except Exception as e:
        logger.error(f"Failed to set watermark for {sync_type}: {e}")
        return False
    finally:
        conn.close()


def get_all_watermarks() -> dict:
    """
    Get all watermarks for this device.

    Returns:
        Dict mapping sync_type to watermark info
    """
    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sync_type, watermark_column, watermark_value,
                       rows_synced, last_sync_at
                FROM argus.sync_watermarks
                WHERE source = %s
            """, (DEVICE_SOURCE,))

            return {
                row[0]: {
                    "column": row[1],
                    "value": row[2],
                    "rows_synced": row[3],
                    "last_sync_at": row[4]
                }
                for row in cur.fetchall()
            }
    except Exception as e:
        logger.error(f"Failed to get watermarks: {e}")
        return {}
    finally:
        conn.close()

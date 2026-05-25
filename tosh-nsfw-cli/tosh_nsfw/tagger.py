"""
Database tagging for NSFW photos.
Uses separate bronze.nsfw_photos table to avoid modifying apple_photos.
"""

import json
import logging
from datetime import datetime

from .scanner import ScanResult
from .utils.db import get_cursor, DatabaseError

logger = logging.getLogger(__name__)


def tag_photo(result: ScanResult, dry_run: bool = False) -> bool:
    """
    Tag a single photo as NSFW in the nsfw_photos table.

    Args:
        result: ScanResult with uuid, score, detections.
        dry_run: If True, don't actually insert.

    Returns:
        True if successful, False otherwise.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would tag {result.uuid} with score {result.max_score:.4f}")
        return True

    detections_json = json.dumps([
        {"label": d.label, "score": d.score}
        for d in result.detections
    ])

    try:
        with get_cursor() as cur:
            # Upsert - update if exists, insert if not
            cur.execute("""
                INSERT INTO bronze.nsfw_photos (uuid, filename, nsfw_score, detections, detected_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (uuid) DO UPDATE SET
                    nsfw_score = EXCLUDED.nsfw_score,
                    detections = EXCLUDED.detections,
                    detected_at = EXCLUDED.detected_at
            """, (result.uuid, result.filename, result.max_score, detections_json, datetime.now()))

            logger.info(f"Tagged {result.uuid} with score {result.max_score:.4f}")
            return True

    except DatabaseError as e:
        logger.error(f"Failed to tag {result.uuid}: {e}")
        return False


def tag_photos(results: list[ScanResult], dry_run: bool = False) -> int:
    """
    Tag multiple photos as NSFW.

    Args:
        results: List of ScanResult objects.
        dry_run: If True, don't actually insert.

    Returns:
        Number of photos tagged.
    """
    tagged = 0

    for result in results:
        if tag_photo(result, dry_run=dry_run):
            tagged += 1

    return tagged


def untag_photo(uuid: str) -> bool:
    """
    Remove NSFW tag from a photo (delete from nsfw_photos table).

    Args:
        uuid: Photo UUID.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                DELETE FROM bronze.nsfw_photos
                WHERE uuid = %s
            """, (uuid,))

            if cur.rowcount == 0:
                logger.warning(f"Photo not found in nsfw_photos: {uuid}")
                return False

            logger.info(f"Untagged {uuid}")
            return True

    except DatabaseError as e:
        logger.error(f"Failed to untag {uuid}: {e}")
        return False


def get_tagged_photos(min_score: float = 0.0) -> list[dict]:
    """
    Get all photos tagged as NSFW, joined with apple_photos for metadata.

    Args:
        min_score: Minimum NSFW score filter.

    Returns:
        List of photo records.
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT
                    n.uuid,
                    n.filename,
                    n.nsfw_score,
                    n.detections,
                    n.detected_at,
                    n.lockboxed_at,
                    n.lockbox_path,
                    p.server_path,
                    p.date_created
                FROM bronze.nsfw_photos n
                LEFT JOIN bronze.apple_photos p ON n.uuid = p.uuid
                WHERE n.nsfw_score >= %s
                  AND n.deleted_at IS NULL
                ORDER BY n.nsfw_score DESC
            """, (min_score,))

            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    except DatabaseError as e:
        logger.error(f"Failed to get tagged photos: {e}")
        return []


def get_tagged_count() -> int:
    """Get count of photos tagged as NSFW."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM bronze.nsfw_photos
                WHERE deleted_at IS NULL
            """)
            return cur.fetchone()[0]

    except DatabaseError as e:
        logger.error(f"Failed to get count: {e}")
        return 0


def mark_lockboxed(uuid: str, lockbox_path: str) -> bool:
    """
    Mark a photo as lockboxed.

    Args:
        uuid: Photo UUID.
        lockbox_path: Path to the lockbox location.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE bronze.nsfw_photos
                SET lockboxed_at = %s,
                    lockbox_path = %s
                WHERE uuid = %s
            """, (datetime.now(), lockbox_path, uuid))

            if cur.rowcount == 0:
                logger.warning(f"Photo not found in nsfw_photos: {uuid}")
                return False

            logger.info(f"Marked {uuid} as lockboxed")
            return True

    except DatabaseError as e:
        logger.error(f"Failed to mark lockboxed: {e}")
        return False


def soft_delete_nsfw(uuid: str) -> bool:
    """
    Soft delete a photo from nsfw_photos table.

    Args:
        uuid: Photo UUID.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with get_cursor() as cur:
            cur.execute("""
                UPDATE bronze.nsfw_photos
                SET deleted_at = %s
                WHERE uuid = %s
                  AND deleted_at IS NULL
            """, (datetime.now(), uuid))

            if cur.rowcount == 0:
                logger.warning(f"Photo not found or already deleted: {uuid}")
                return False

            logger.info(f"Soft deleted {uuid} from nsfw_photos")
            return True

    except DatabaseError as e:
        logger.error(f"Failed to soft delete: {e}")
        return False

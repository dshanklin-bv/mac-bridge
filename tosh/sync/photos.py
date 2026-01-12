"""
Sync Photos to bronze.apple_photos and transfer files to server.
Uses osxphotos library for robust Photos database access and iCloud handling.
"""

import logging
import subprocess
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import osxphotos
from psycopg2.extras import execute_values

from tosh.utils.db import get_connection
from tosh.utils.watermark import get_watermark, set_watermark

logger = logging.getLogger(__name__)

# Server destination
SERVER_HOST = "rhea-dev"
SERVER_BASE_PATH = "/home/dshanklin/data/photos/originals"

BATCH_SIZE = 500


def transfer_file(local_path: Path, server_path: str) -> bool:
    """Transfer a file to the server via rsync."""
    try:
        # Create remote directory
        remote_dir = os.path.dirname(server_path)
        subprocess.run(
            ["ssh", SERVER_HOST, f"mkdir -p {remote_dir}"],
            check=True,
            capture_output=True
        )

        # Transfer file
        subprocess.run(
            ["rsync", "-az", str(local_path), f"{SERVER_HOST}:{server_path}"],
            check=True,
            capture_output=True
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"File transfer failed: {e}")
        return False


def get_server_path(photo: osxphotos.PhotoInfo) -> str:
    """Generate server path based on photo date and UUID."""
    if photo.date:
        year = str(photo.date.year)
        month = f"{photo.date.month:02d}"
    else:
        year = "unknown"
        month = "00"

    # Get extension from filename or path
    if photo.path:
        ext = Path(photo.path).suffix
    elif photo.filename:
        ext = Path(photo.filename).suffix
    else:
        ext = ".heic"

    return f"{SERVER_BASE_PATH}/{year}/{month}/{photo.uuid}{ext}"


def sync(transfer_files: bool = False) -> int:
    """
    Sync photos to bronze layer and optionally transfer files.

    Uses osxphotos library for robust Photos database access.

    Args:
        transfer_files: Whether to transfer actual files to server.

    Returns:
        Number of records synced.
    """
    # Get current watermark (ISO timestamp)
    watermark_str = get_watermark("photos")
    watermark_dt = None
    if watermark_str:
        try:
            watermark_dt = datetime.fromisoformat(watermark_str)
            logger.info(f"Using watermark: date_modified > {watermark_dt}")
        except ValueError:
            logger.warning(f"Invalid watermark format: {watermark_str}")
    else:
        logger.info("No watermark found, doing full sync")

    logger.info("Opening Photos library with osxphotos...")
    photosdb = osxphotos.PhotosDB()
    logger.info(f"Library contains {len(photosdb)} photos")

    # Get all photos (not in trash)
    all_photos = photosdb.photos(intrash=False)
    logger.info(f"Found {len(all_photos)} photos (excluding trash)")

    # Filter by watermark if set
    if watermark_dt:
        # Convert watermark to naive datetime for comparison if needed
        if watermark_dt.tzinfo:
            watermark_dt = watermark_dt.replace(tzinfo=None)
        all_photos = [p for p in all_photos if p.date_modified and p.date_modified.replace(tzinfo=None) > watermark_dt]
        logger.info(f"After watermark filter: {len(all_photos)} photos")

    if not all_photos:
        logger.info("No new photos to sync")
        return 0

    # Track stats
    local_count = 0
    icloud_count = 0
    max_mod_date = None

    # Build photo records
    photo_records = []
    for photo in all_photos:
        # Track max modification date for watermark
        if photo.date_modified:
            mod_dt = photo.date_modified.replace(tzinfo=None) if photo.date_modified.tzinfo else photo.date_modified
            if max_mod_date is None or mod_dt > max_mod_date:
                max_mod_date = mod_dt

        # Determine sync status based on local availability
        if photo.path and Path(photo.path).exists():
            sync_status = "pending"  # Local, ready to transfer
            local_count += 1
        elif photo.incloud:
            sync_status = "in_cloud"  # Needs iCloud download
            icloud_count += 1
        else:
            sync_status = "missing"  # Not available
            icloud_count += 1

        # Get server path
        server_path = get_server_path(photo)

        # Build record
        photo_records.append({
            'uuid': photo.uuid,
            'filename': photo.filename,
            'original_filename': photo.original_filename,
            'local_path': photo.path if photo.path else None,
            'date_created': photo.date.isoformat() if photo.date else None,
            'date_modified': photo.date_modified.isoformat() if photo.date_modified else None,
            'date_added': photo.date_added.isoformat() if photo.date_added else None,
            'width': photo.width,
            'height': photo.height,
            'orientation': photo.orientation,
            'latitude': photo.latitude,
            'longitude': photo.longitude,
            'is_favorite': photo.favorite,
            'is_hidden': photo.hidden,
            'is_screenshot': photo.screenshot,
            'is_video': photo.ismovie,
            'is_raw': photo.israw,
            'is_live_photo': photo.live_photo,
            'is_missing': photo.ismissing,
            'in_cloud': photo.incloud,
            'title': photo.title,
            'description': photo.description,
            'keywords': photo.keywords if photo.keywords else [],
            'albums': photo.albums if photo.albums else [],
            'persons': photo.persons if photo.persons else [],
            'server_path': server_path,
            'sync_status': sync_status
        })

    logger.info(f"Photos: {local_count} local, {icloud_count} in iCloud")

    # Insert to database
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            values = [(
                r['uuid'], r['filename'], r['original_filename'], r['local_path'],
                r['date_created'], r['date_modified'], r['date_added'],
                r['width'], r['height'], r['orientation'],
                r['latitude'], r['longitude'],
                r['is_favorite'], r['is_hidden'], r['is_screenshot'],
                r['is_video'], r['is_raw'], r['is_live_photo'],
                r['is_missing'], r['in_cloud'],
                r['title'], r['description'],
                r['keywords'], r['albums'], r['persons'],
                r['server_path'], r['sync_status']
            ) for r in photo_records]

            sql = """
                INSERT INTO bronze.apple_photos (
                    uuid, filename, original_filename, local_path,
                    date_created, date_modified, date_added,
                    width, height, orientation,
                    latitude, longitude,
                    is_favorite, is_hidden, is_screenshot,
                    is_video, is_raw, is_live_photo,
                    is_missing, in_cloud,
                    title, description,
                    keywords, albums, persons,
                    server_path, sync_status
                )
                VALUES %s
                ON CONFLICT (uuid) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    local_path = EXCLUDED.local_path,
                    date_modified = EXCLUDED.date_modified,
                    is_favorite = EXCLUDED.is_favorite,
                    is_hidden = EXCLUDED.is_hidden,
                    is_missing = EXCLUDED.is_missing,
                    in_cloud = EXCLUDED.in_cloud,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    keywords = EXCLUDED.keywords,
                    albums = EXCLUDED.albums,
                    persons = EXCLUDED.persons,
                    sync_status = CASE
                        WHEN bronze.apple_photos.sync_status = 'synced' THEN 'synced'
                        ELSE EXCLUDED.sync_status
                    END,
                    synced_at = NOW()
            """
            execute_values(cur, sql, values, page_size=BATCH_SIZE)

        conn.commit()
        logger.info(f"Upserted {len(photo_records)} photo records to bronze")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Transfer local files if enabled
    if transfer_files:
        local_photos = [r for r in photo_records if r['sync_status'] == 'pending' and r['local_path']]
        logger.info(f"Transferring {len(local_photos)} local photos...")

        transferred = 0
        failed = 0

        for r in local_photos:
            local_path = Path(r['local_path'])
            if local_path.exists():
                if transfer_file(local_path, r['server_path']):
                    transferred += 1
                    update_sync_status(r['uuid'], 'synced')
                else:
                    failed += 1
                    update_sync_status(r['uuid'], 'failed')
            else:
                failed += 1
                logger.warning(f"File not found: {r['local_path']}")

        logger.info(f"Transferred {transferred} files, {failed} failed")

    # Update watermark
    if max_mod_date:
        set_watermark("photos", "date_modified", max_mod_date.isoformat(), len(photo_records))

    return len(photo_records)


def update_sync_status(uuid: str, status: str):
    """Update sync status for a photo by UUID."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bronze.apple_photos
                SET sync_status = %s, synced_at = NOW()
                WHERE uuid = %s
            """, (status, uuid))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update sync status: {e}")


def export_from_icloud(limit: int = 100, dest_dir: str = "/tmp/photos_export") -> int:
    """
    Export photos from iCloud using osxphotos CLI.

    This triggers Photos.app to download from iCloud.

    Args:
        limit: Maximum number of photos to export
        dest_dir: Local directory to export to

    Returns:
        Number of photos exported
    """
    import shutil

    # Create export directory
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting up to {limit} iCloud photos to {dest_dir}")

    # Get photos that are in_cloud status
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT uuid, server_path FROM bronze.apple_photos
                WHERE sync_status = 'in_cloud'
                LIMIT %s
            """, (limit,))
            pending = cur.fetchall()
    finally:
        conn.close()

    if not pending:
        logger.info("No iCloud photos pending export")
        return 0

    uuids = [row[0] for row in pending]
    uuid_to_server_path = {row[0]: row[1] for row in pending}

    logger.info(f"Found {len(uuids)} photos to export from iCloud")

    # Use osxphotos CLI with --download-missing
    # Export specific UUIDs
    uuid_args = " ".join([f"--uuid {u}" for u in uuids[:limit]])

    try:
        result = subprocess.run(
            f"osxphotos export {dest_dir} --download-missing {uuid_args}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        logger.info(f"Export stdout: {result.stdout[:500]}")
        if result.returncode != 0:
            logger.error(f"Export failed: {result.stderr}")
            return 0

    except subprocess.TimeoutExpired:
        logger.error("Export timed out")
        return 0
    except Exception as e:
        logger.error(f"Export error: {e}")
        return 0

    # Find exported files and transfer to server
    exported_count = 0
    for uuid in uuids:
        # Find the exported file
        for f in Path(dest_dir).rglob(f"*{uuid}*"):
            if f.is_file():
                server_path = uuid_to_server_path.get(uuid)
                if server_path and transfer_file(f, server_path):
                    update_sync_status(uuid, 'synced')
                    exported_count += 1
                    # Clean up local export
                    f.unlink()
                break

    logger.info(f"Exported and transferred {exported_count} photos from iCloud")
    return exported_count

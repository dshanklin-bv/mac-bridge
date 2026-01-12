"""
tosh photos - Photo-specific operations.

Usage:
    python -m tosh.cli.photos stats        # Show photo stats
    python -m tosh.cli.photos download     # Download iCloud photos
    python -m tosh.cli.photos transfer     # Transfer local photos to server

For iCloud downloads, run this command periodically or leave running overnight.
Downloads are slow (~1 photo per 2 minutes via AppleScript).
"""

import argparse
import sys
import time
from pathlib import Path

from tosh.utils.db import test_connection, get_connection
from tosh.utils.logging import setup_logging, get_logger, new_correlation_id
from tosh.sync.photos import transfer_file, update_sync_status, get_server_path


def show_stats():
    """Show photo sync statistics."""
    logger = get_logger(__name__)

    if not test_connection():
        logger.error("Database connection failed")
        return 1

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN sync_status = 'synced' THEN 1 ELSE 0 END) as synced,
            SUM(CASE WHEN sync_status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN sync_status = 'in_cloud' THEN 1 ELSE 0 END) as in_cloud,
            SUM(CASE WHEN sync_status = 'missing' THEN 1 ELSE 0 END) as missing,
            SUM(CASE WHEN is_favorite THEN 1 ELSE 0 END) as favorites,
            SUM(CASE WHEN is_video THEN 1 ELSE 0 END) as videos
        FROM bronze.apple_photos
    """)
    row = cur.fetchone()

    print("\n📊 Photo Sync Statistics")
    print("=" * 40)
    print(f"Total photos:    {row[0]:,}")
    print(f"  ✅ Synced:     {row[1]:,}")
    print(f"  📤 Pending:    {row[2]:,}")
    print(f"  ☁️  In iCloud:  {row[3]:,}")
    print(f"  ❌ Missing:    {row[4]:,}")
    print()
    print(f"  ⭐ Favorites:  {row[5]:,}")
    print(f"  🎬 Videos:     {row[6]:,}")

    # Show breakdown by year
    cur.execute("""
        SELECT
            EXTRACT(YEAR FROM date_created::timestamp)::int as year,
            COUNT(*) as count
        FROM bronze.apple_photos
        WHERE date_created IS NOT NULL
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 10
    """)

    print("\n📅 Photos by Year (top 10)")
    print("-" * 25)
    for row in cur.fetchall():
        print(f"  {int(row[0])}: {row[1]:,}")

    conn.close()
    return 0


def download_icloud(limit: int = 100, batch_size: int = 10):
    """Download photos from iCloud and transfer to server."""
    import osxphotos
    import subprocess

    logger = get_logger(__name__)

    if not test_connection():
        logger.error("Database connection failed")
        return 1

    conn = get_connection()
    cur = conn.cursor()

    # Get photos that need downloading
    cur.execute("""
        SELECT uuid, server_path
        FROM bronze.apple_photos
        WHERE sync_status = 'in_cloud'
        ORDER BY date_created DESC
        LIMIT %s
    """, (limit,))
    pending = cur.fetchall()
    conn.close()

    if not pending:
        print("No iCloud photos pending download")
        return 0

    print(f"Found {len(pending)} iCloud photos to download")
    print(f"Processing in batches of {batch_size}")
    print("This will be slow - each photo takes ~2 minutes")
    print()

    # Create temp export directory
    export_dir = Path("/tmp/tosh_icloud_export")
    export_dir.mkdir(exist_ok=True)

    # Process in batches
    downloaded = 0
    failed = 0

    for i in range(0, len(pending), batch_size):
        batch = pending[i:i+batch_size]
        uuids = [p[0] for p in batch]
        uuid_to_server = {p[0]: p[1] for p in batch}

        print(f"\nBatch {i//batch_size + 1}: Downloading {len(batch)} photos...")

        # Build osxphotos command
        uuid_args = " ".join([f"--uuid {u}" for u in uuids])
        cmd = f"osxphotos export {export_dir} --download-missing {uuid_args}"

        try:
            start = time.time()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=1800  # 30 min per batch
            )
            elapsed = time.time() - start

            if result.returncode != 0:
                logger.error(f"Export failed: {result.stderr[:200]}")
                failed += len(batch)
                continue

            # Find and transfer exported files
            for uuid in uuids:
                found = False
                for f in export_dir.rglob(f"*"):
                    if uuid in f.name and f.is_file():
                        server_path = uuid_to_server[uuid]
                        if transfer_file(f, server_path):
                            update_sync_status(uuid, 'synced')
                            downloaded += 1
                            f.unlink()  # Clean up
                        else:
                            update_sync_status(uuid, 'failed')
                            failed += 1
                        found = True
                        break

                if not found:
                    failed += 1

            print(f"  Batch complete: {elapsed:.1f}s ({elapsed/len(batch):.1f}s per photo)")

        except subprocess.TimeoutExpired:
            logger.error("Batch timed out")
            failed += len(batch)
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            break

    print(f"\n✅ Downloaded: {downloaded}")
    print(f"❌ Failed: {failed}")

    return 0 if failed == 0 else 1


def transfer_local():
    """Transfer any local photos that haven't been synced."""
    logger = get_logger(__name__)

    if not test_connection():
        logger.error("Database connection failed")
        return 1

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT uuid, local_path, server_path
        FROM bronze.apple_photos
        WHERE sync_status = 'pending' AND local_path IS NOT NULL
    """)
    pending = cur.fetchall()
    conn.close()

    if not pending:
        print("No local photos pending transfer")
        return 0

    print(f"Transferring {len(pending)} local photos...")

    transferred = 0
    failed = 0

    for uuid, local_path, server_path in pending:
        if Path(local_path).exists():
            print(f"  {Path(local_path).name}")
            if transfer_file(Path(local_path), server_path):
                update_sync_status(uuid, 'synced')
                transferred += 1
            else:
                failed += 1
        else:
            failed += 1

    print(f"\n✅ Transferred: {transferred}")
    print(f"❌ Failed: {failed}")

    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description='Photo-specific operations')
    parser.add_argument(
        'command',
        choices=['stats', 'download', 'transfer'],
        help='Command to run'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Max photos to process (default: 100)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Photos per batch for download (default: 10)'
    )

    args = parser.parse_args()

    setup_logging(json_format=False)
    new_correlation_id()

    if args.command == 'stats':
        sys.exit(show_stats())
    elif args.command == 'download':
        sys.exit(download_icloud(limit=args.limit, batch_size=args.batch_size))
    elif args.command == 'transfer':
        sys.exit(transfer_local())


if __name__ == '__main__':
    main()

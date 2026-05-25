#!/usr/bin/env python3
"""
Mac Sync Daemon - Sync Mac data to comms database on pg-rhea.

Syncs:
- Apple Messages (iMessage/SMS) from chat.db
- Apple Call History from CallHistory.storedata
- Apple Contacts from AddressBook

Usage:
    python -m mac_sync_daemon.main [--once] [--source SOURCE]

Options:
    --once          Run once and exit (default: continuous loop)
    --source        Only sync specific source (messages, calls, contacts, all)
    --full          Full resync (reset watermarks)
"""

import argparse
import logging
import time
import sys

from .db import get_db, close_db
from .sources import (
    sync_messages,
    sync_handles,
    sync_chats,
    sync_calls,
    sync_contacts,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYNC_INTERVAL = 300  # 5 minutes


def sync_all_messages():
    """Sync all message-related tables."""
    total = 0
    total += sync_handles()
    total += sync_chats()
    total += sync_messages()
    return total


def run_sync(source: str = 'all') -> dict:
    """Run sync for specified source(s)."""
    results = {}

    try:
        # Ensure we have a database connection
        db = get_db()
        logger.info("Connected to comms database")

        if source in ('all', 'messages'):
            results['handles'] = sync_handles()
            results['chats'] = sync_chats()
            results['messages'] = sync_messages()

        if source in ('all', 'calls'):
            results['calls'] = sync_calls()

        if source in ('all', 'contacts'):
            results['contacts'] = sync_contacts()

        logger.info(f"Sync complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise


def reset_watermarks(source: str = 'all'):
    """Reset sync watermarks for full resync."""
    db = get_db()

    sources_to_reset = []
    if source in ('all', 'messages'):
        sources_to_reset.extend(['apple_messages', 'apple_handles', 'apple_chats'])
    if source in ('all', 'calls'):
        sources_to_reset.append('apple_calls')
    if source in ('all', 'contacts'):
        sources_to_reset.append('apple_contacts')

    with db.cursor() as cur:
        for src in sources_to_reset:
            cur.execute("""
                UPDATE sync.sources
                SET last_sync_id = 0,
                    sync_status = 'pending',
                    updated_at = NOW()
                WHERE name = %s
            """, (src,))
            logger.info(f"Reset watermark for {src}")


def main():
    parser = argparse.ArgumentParser(description='Sync Mac data to comms database')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--source', default='all',
                        choices=['all', 'messages', 'calls', 'contacts'],
                        help='Source to sync')
    parser.add_argument('--full', action='store_true', help='Full resync')
    parser.add_argument('--interval', type=int, default=SYNC_INTERVAL,
                        help='Sync interval in seconds (default: 300)')

    args = parser.parse_args()

    logger.info("Mac Sync Daemon starting...")
    logger.info(f"Source: {args.source}, Once: {args.once}, Full: {args.full}")

    try:
        if args.full:
            logger.info("Resetting watermarks for full resync...")
            reset_watermarks(args.source)

        if args.once:
            run_sync(args.source)
        else:
            while True:
                try:
                    run_sync(args.source)
                except Exception as e:
                    logger.error(f"Sync iteration failed: {e}")

                logger.info(f"Sleeping {args.interval}s until next sync...")
                time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        close_db()

    return 0


if __name__ == '__main__':
    sys.exit(main())

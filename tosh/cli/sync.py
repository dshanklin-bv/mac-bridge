"""
tosh sync - Sync Apple data to bronze tables.

Usage:
    python -m tosh.cli.sync --source all
    python -m tosh.cli.sync --source messages
    python -m tosh.cli.sync --source calls,contacts
    python -m tosh.cli.sync --source all --json  # JSON logs
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Dict, Optional

from tosh.utils.db import test_connection, get_argus_connection
from tosh.utils.logging import (
    setup_logging, get_logger, new_correlation_id,
    get_correlation_id, SyncMetrics
)
from tosh.utils.health import record_sync_success, record_sync_failure
from tosh.sync import messages, calls, contacts, photos

# Available sync sources
SOURCES = {
    'messages': messages.sync,
    'calls': calls.sync,
    'contacts': contacts.sync,
    'photos': photos.sync,
    # TODO: Add calendar and notes
    # 'calendar': calendar.sync,
    # 'notes': notes.sync,
}

# Device identifier for sync events
DEVICE_SOURCE = "tosh-mac"


def record_console_event(
    correlation_id: str,
    event_type: str,
    severity: str,
    title: str,
    message: str,
    source: str,
    rows: int = 0,
    duration_ms: int = 0,
    error: Optional[str] = None
):
    """
    Record a console event to argus.console_events for centralized observability.

    Args:
        correlation_id: Sync run correlation ID
        event_type: 'sync', 'sync_complete', 'sync_error', 'warning'
        severity: 'info', 'warning', 'error'
        title: Short title for the event
        message: Longer description
        source: Source name (messages, calls, contacts)
        rows: Number of rows synced
        duration_ms: Duration in milliseconds
        error: Error message if applicable
    """
    logger = get_logger(__name__)

    metadata = {
        "correlation_id": correlation_id,
        "source": source,
        "rows": rows,
        "duration_ms": duration_ms
    }
    if error:
        metadata["error"] = error

    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO argus.console_events (
                    id, service_id, source, event_type, severity,
                    title, message, metadata, created_at
                ) VALUES (
                    gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, NOW()
                )
            """, (
                'mac-bridge',
                'tosh',
                event_type,
                severity,
                title,
                message,
                json.dumps(metadata)
            ))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to record console event: {e}")
    finally:
        conn.close()


def record_sync_event(
    run_id: str,
    status: str,
    sources_synced: List[str],
    row_counts: Dict[str, int],
    started_at: datetime,
    completed_at: datetime,
    error_message: Optional[str] = None
):
    """
    Record a sync event to argus.sync_events for ETL triggering.

    Args:
        run_id: Correlation ID for this sync run
        status: 'completed' or 'failed'
        sources_synced: List of sources that were synced
        row_counts: Dict mapping source name to row count
        started_at: When sync started
        completed_at: When sync completed
        error_message: Error message if status is 'failed'
    """
    logger = get_logger(__name__)

    try:
        conn = get_argus_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO argus.sync_events (
                    source, run_id, status, sources_synced, row_counts,
                    started_at, completed_at, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                DEVICE_SOURCE,
                run_id,
                status,
                sources_synced,
                json.dumps(row_counts),
                started_at,
                completed_at,
                error_message
            ))
        conn.commit()
        logger.info("Sync event recorded", run_id=run_id, status=status)
    except Exception as e:
        logger.error(f"Failed to record sync event: {e}", run_id=run_id)
    finally:
        conn.close()


def run_sync(sources: List[str], json_logs: bool = True) -> int:
    """
    Run sync for specified sources.

    Args:
        sources: List of source names to sync.
        json_logs: Use JSON log format.

    Returns:
        Exit code (0 = success, non-zero = failure).
    """
    # Initialize logging and correlation ID
    setup_logging(json_format=json_logs)
    correlation_id = new_correlation_id()
    logger = get_logger(__name__)

    started_at = datetime.now(timezone.utc)
    logger.info("Sync run starting", correlation_id=correlation_id, sources=sources)

    # Test database connection first
    logger.info("Testing database connection")
    if not test_connection():
        logger.error("Database connection failed - is SSH tunnel running?")
        return 2

    logger.info("Database connection OK")

    failed = []
    row_counts: Dict[str, int] = {}
    sources_synced: List[str] = []

    for source in sources:
        if source not in SOURCES:
            logger.warning(f"Unknown source: {source}", source=source)
            continue

        metrics = SyncMetrics(source)
        logger.info(f"Starting sync: {source}", source=source)

        try:
            count = SOURCES[source]()
            metrics.rows_read = count
            metrics.rows_written = count
            metrics.complete(success=True)
            metrics.log_summary()

            # Track for sync event
            row_counts[source] = count
            sources_synced.append(source)

            # Record health status
            record_sync_success(
                source=source,
                rows_synced=count,
                duration_ms=metrics.duration_ms,
                correlation_id=correlation_id
            )

            # Record console event for observability
            record_console_event(
                correlation_id=correlation_id,
                event_type='sync_complete',
                severity='info',
                title=f'Sync complete: {source}',
                message=f'Synced {count} rows in {metrics.duration_ms}ms',
                source=source,
                rows=count,
                duration_ms=metrics.duration_ms
            )

        except Exception as e:
            error_msg = str(e)
            metrics.complete(success=False, error=error_msg)
            metrics.log_summary()

            # Record health status
            record_sync_failure(
                source=source,
                error=error_msg,
                correlation_id=correlation_id
            )

            # Record console event for error
            record_console_event(
                correlation_id=correlation_id,
                event_type='sync_error',
                severity='error',
                title=f'Sync failed: {source}',
                message=f'Error: {error_msg}',
                source=source,
                rows=0,
                duration_ms=metrics.duration_ms,
                error=error_msg
            )

            failed.append(source)

    completed_at = datetime.now(timezone.utc)

    # Record sync event for ETL triggering
    if sources_synced:
        record_sync_event(
            run_id=correlation_id,
            status='failed' if failed else 'completed',
            sources_synced=sources_synced,
            row_counts=row_counts,
            started_at=started_at,
            completed_at=completed_at,
            error_message=f"Failed sources: {', '.join(failed)}" if failed else None
        )

    if failed:
        logger.error("Sync completed with failures", failed_sources=failed)
        return 1

    logger.info("Sync completed successfully", sources=sources)
    return 0


def main():
    parser = argparse.ArgumentParser(description='Sync Apple data to bronze tables')
    parser.add_argument(
        '--source',
        type=str,
        default='all',
        help='Sources to sync: all, messages, calls, contacts (comma-separated)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        default=True,
        help='Use JSON log format (default: True)'
    )
    parser.add_argument(
        '--human',
        action='store_true',
        help='Use human-readable log format'
    )

    args = parser.parse_args()

    if args.source == 'all':
        sources = list(SOURCES.keys())
    else:
        sources = [s.strip() for s in args.source.split(',')]

    json_logs = not args.human

    sys.exit(run_sync(sources, json_logs=json_logs))


if __name__ == '__main__':
    main()

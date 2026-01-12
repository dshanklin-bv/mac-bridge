"""
Health status tracking for tosh daemon.
Writes last successful sync timestamps per source for quick health checks.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .config import get

# Default status file location
DEFAULT_STATUS_FILE = Path.home() / ".tosh" / "health.json"


def _get_status_file() -> Path:
    """Get the health status file path from config or default."""
    path_str = get("paths.health_file")
    if path_str:
        return Path(path_str).expanduser()
    return DEFAULT_STATUS_FILE


def _load_status() -> Dict[str, Any]:
    """Load current status from file."""
    status_file = _get_status_file()
    if not status_file.exists():
        return {"sources": {}, "last_run": None}

    try:
        with open(status_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"sources": {}, "last_run": None}


def _save_status(status: Dict[str, Any]):
    """Save status to file."""
    status_file = _get_status_file()
    status_file.parent.mkdir(parents=True, exist_ok=True)

    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2)


def record_sync_success(source: str, rows_synced: int, duration_ms: int,
                        correlation_id: Optional[str] = None):
    """
    Record a successful sync for a source.

    Args:
        source: Source name (messages, calls, contacts)
        rows_synced: Number of rows synced
        duration_ms: Duration in milliseconds
        correlation_id: Optional correlation ID for tracing
    """
    status = _load_status()

    now = datetime.utcnow().isoformat() + "Z"

    status["sources"][source] = {
        "last_success": now,
        "rows_synced": rows_synced,
        "duration_ms": duration_ms,
        "correlation_id": correlation_id,
    }
    status["last_run"] = now

    _save_status(status)


def record_sync_failure(source: str, error: str,
                        correlation_id: Optional[str] = None):
    """
    Record a failed sync for a source.

    Args:
        source: Source name
        error: Error message
        correlation_id: Optional correlation ID
    """
    status = _load_status()

    now = datetime.utcnow().isoformat() + "Z"

    # Preserve last_success, update last_failure
    if source not in status["sources"]:
        status["sources"][source] = {}

    status["sources"][source]["last_failure"] = now
    status["sources"][source]["last_error"] = error
    status["sources"][source]["error_correlation_id"] = correlation_id
    status["last_run"] = now

    _save_status(status)


def get_health_status() -> Dict[str, Any]:
    """
    Get current health status.

    Returns:
        Dict with health info:
        {
            "healthy": bool,
            "last_run": "2024-01-11T12:00:00Z",
            "sources": {
                "messages": {
                    "last_success": "...",
                    "rows_synced": 58000,
                    "duration_ms": 3000
                },
                ...
            }
        }
    """
    status = _load_status()

    # Determine overall health
    # Healthy if: last_run exists and all sources have recent success
    healthy = bool(status.get("last_run"))
    for source_status in status.get("sources", {}).values():
        # If there's a failure after the last success, not healthy
        last_success = source_status.get("last_success")
        last_failure = source_status.get("last_failure")
        if last_failure and (not last_success or last_failure > last_success):
            healthy = False
            break

    return {
        "healthy": healthy,
        "last_run": status.get("last_run"),
        "sources": status.get("sources", {}),
    }


def print_health_status():
    """Print human-readable health status."""
    status = get_health_status()

    print(f"Health: {'OK' if status['healthy'] else 'DEGRADED'}")
    print(f"Last run: {status['last_run'] or 'Never'}")
    print()

    for source, info in status.get("sources", {}).items():
        print(f"{source}:")
        if info.get("last_success"):
            print(f"  Last success: {info['last_success']}")
            print(f"  Rows synced: {info.get('rows_synced', 'N/A')}")
            print(f"  Duration: {info.get('duration_ms', 'N/A')}ms")
        if info.get("last_failure"):
            print(f"  Last failure: {info['last_failure']}")
            print(f"  Error: {info.get('last_error', 'Unknown')}")
        print()

"""
Structured logging for tosh daemon.
Provides JSON-formatted logs with correlation IDs for tracing sync runs.
"""

import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Context variable for correlation ID (thread-safe)
_correlation_id: ContextVar[str] = ContextVar('correlation_id', default='')


def new_correlation_id() -> str:
    """Generate and set a new correlation ID for the current sync run."""
    cid = f"sync_{uuid.uuid4().hex[:12]}"
    _correlation_id.set(cid)
    return cid


def get_correlation_id() -> str:
    """Get the current correlation ID."""
    return _correlation_id.get() or "no_correlation"


class JsonFormatter(logging.Formatter):
    """
    JSON log formatter with correlation ID support.

    Output format:
    {"ts": "2024-01-11T12:00:00", "level": "INFO", "cid": "sync_abc123",
     "logger": "tosh.sync.messages", "msg": "...", "extra": {...}}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "cid": get_correlation_id(),
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Add any extra fields passed via logging calls
        if hasattr(record, 'extra') and record.extra:
            log_entry["extra"] = record.extra

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class StructuredLogger:
    """
    Wrapper around standard logger with structured logging support.

    Usage:
        logger = get_logger(__name__)
        logger.info("Syncing messages", rows_read=1000, duration_ms=150)
    """

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(self, level: int, msg: str, **kwargs):
        """Log with extra fields."""
        extra = kwargs if kwargs else None
        record = self._logger.makeRecord(
            self._logger.name, level, "", 0, msg, (), None
        )
        if extra:
            record.extra = extra
        self._logger.handle(record)

    def debug(self, msg: str, **kwargs):
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)

    def exception(self, msg: str, **kwargs):
        """Log error with exception traceback."""
        self._logger.exception(msg, extra={'extra': kwargs} if kwargs else None)


# Module-level logger cache
_loggers: Dict[str, StructuredLogger] = {}


def setup_logging(json_format: bool = True, level: int = logging.INFO):
    """
    Configure root logger for structured logging.

    Args:
        json_format: Use JSON format (True) or human-readable (False)
        level: Logging level
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Add new handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        # Add filter that injects cid into every record
        class CorrelationIdFilter(logging.Filter):
            def filter(self, record):
                record.cid = get_correlation_id()
                return True
        handler.addFilter(CorrelationIdFilter())
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s (%(cid)s): %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

    root.addHandler(handler)


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger by name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(logging.getLogger(name))
    return _loggers[name]


class SyncMetrics:
    """
    Metrics collector for a single sync run.

    Usage:
        metrics = SyncMetrics("messages")
        metrics.rows_read = 58000
        metrics.rows_written = 58000
        metrics.complete()
        metrics.log_summary()
    """

    def __init__(self, source: str):
        self.source = source
        self.correlation_id = get_correlation_id()
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None
        self.rows_read = 0
        self.rows_written = 0
        self.success = False
        self.error: Optional[str] = None
        self._logger = get_logger(f"tosh.metrics.{source}")

    @property
    def duration_ms(self) -> int:
        """Duration in milliseconds."""
        end = self.end_time or datetime.utcnow()
        return int((end - self.start_time).total_seconds() * 1000)

    def complete(self, success: bool = True, error: Optional[str] = None):
        """Mark sync as complete."""
        self.end_time = datetime.utcnow()
        self.success = success
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "source": self.source,
            "correlation_id": self.correlation_id,
            "start_time": self.start_time.isoformat() + "Z",
            "end_time": self.end_time.isoformat() + "Z" if self.end_time else None,
            "duration_ms": self.duration_ms,
            "rows_read": self.rows_read,
            "rows_written": self.rows_written,
            "success": self.success,
            "error": self.error,
        }

    def log_summary(self):
        """Log a summary of this sync run."""
        if self.success:
            self._logger.info(
                f"Sync complete: {self.source}",
                **self.to_dict()
            )
        else:
            self._logger.error(
                f"Sync failed: {self.source}",
                **self.to_dict()
            )

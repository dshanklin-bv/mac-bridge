"""
Database connection utilities for tosh daemon.
Connects to comms database via localhost (SSH tunnel).
"""

import logging
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection

from .keychain import get_db_password, KeychainError
from .config import get

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


def _get_db_config() -> dict:
    """Get database config from config file."""
    return {
        "host": get("database.host", "localhost"),
        "port": get("database.port", 15432),
        "database": get("database.name", "comms"),
        "user": get("database.user", "postgres"),
    }


def get_connection() -> connection:
    """
    Get a database connection using Keychain credentials.

    Returns:
        psycopg2 connection object.

    Raises:
        DatabaseError: If connection fails.
    """
    try:
        password = get_db_password()
    except KeychainError as e:
        raise DatabaseError(f"Failed to get credentials: {e}")

    db_config = _get_db_config()
    port = db_config["port"]

    try:
        conn = psycopg2.connect(
            **db_config,
            password=password,
            connect_timeout=10
        )
        return conn
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        if "could not connect" in error_msg or "connection refused" in error_msg:
            raise DatabaseError(
                f"Cannot connect to database. Is SSH tunnel running? "
                f"Check: nc -z localhost {port}"
            )
        raise DatabaseError(f"Database connection failed: {e}")


@contextmanager
def get_cursor() -> Generator:
    """
    Context manager for database cursor.

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT ...")

    Automatically commits on success, rolls back on error.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_connection() -> bool:
    """
    Test database connectivity.

    Returns:
        True if connection successful, False otherwise.
    """
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except DatabaseError as e:
        logger.warning(f"Database connection test failed: {e}")
        return False


def get_argus_connection() -> connection:
    """
    Get connection to argus database (for messaging).

    Returns:
        psycopg2 connection object.
    """
    try:
        password = get_db_password()
    except KeychainError as e:
        raise DatabaseError(f"Failed to get credentials: {e}")

    try:
        conn = psycopg2.connect(
            host=get("argus.host", "localhost"),
            port=get("argus.port", 15432),
            database=get("argus.name", "argus"),
            user=get("argus.user", "postgres"),
            password=password,
            connect_timeout=10
        )
        return conn
    except psycopg2.OperationalError as e:
        raise DatabaseError(f"Argus database connection failed: {e}")

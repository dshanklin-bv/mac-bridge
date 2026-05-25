"""
Database connection utilities for tosh-nsfw-cli.
Reuses tosh keychain credentials and SSH tunnel.
"""

import logging
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import psycopg2
import yaml
from psycopg2.extensions import connection

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".config" / "tosh" / "config.yaml"
KEYCHAIN_SERVICE = "tosh-comms-db"
KEYCHAIN_ACCOUNT = "postgres"


class DatabaseError(Exception):
    """Raised when database operations fail."""
    pass


class KeychainError(Exception):
    """Raised when Keychain access fails."""
    pass


def _get_db_password() -> str:
    """Retrieve database password from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password",
             "-s", KEYCHAIN_SERVICE,
             "-a", KEYCHAIN_ACCOUNT,
             "-w"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            raise KeychainError(
                f"Keychain credential not found. Ensure tosh is configured. "
                f"Service: {KEYCHAIN_SERVICE}"
            )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise KeychainError("Keychain access timed out")


def _load_config() -> dict[str, Any]:
    """Load tosh config file."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _get_config(key: str, default: Any = None) -> Any:
    """Get config value by dot-notation key."""
    config = _load_config()
    keys = key.split('.')
    value = config
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default
    return value


def get_connection() -> connection:
    """
    Get a database connection using Keychain credentials.

    Returns:
        psycopg2 connection object.

    Raises:
        DatabaseError: If connection fails.
    """
    try:
        password = _get_db_password()
    except KeychainError as e:
        raise DatabaseError(f"Failed to get credentials: {e}")

    host = _get_config("database.host", "localhost")
    port = _get_config("database.port", 15432)
    database = _get_config("database.name", "comms")
    user = _get_config("database.user", "postgres")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
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
    """Test database connectivity."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            return True
    except DatabaseError as e:
        logger.warning(f"Database connection test failed: {e}")
        return False

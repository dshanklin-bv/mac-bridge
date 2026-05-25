"""Database connection via SSH tunnel to pg-rhea."""

import subprocess
import psycopg2
from contextlib import contextmanager
from sshtunnel import SSHTunnelForwarder

from . import config


class DatabaseConnection:
    """Manages connection to pg-rhea via SSH tunnel."""

    def __init__(self):
        self.tunnel = None
        self.conn = None

    def connect_via_tunnel(self):
        """Connect to pg-rhea through SSH tunnel."""
        # Create SSH tunnel
        self.tunnel = SSHTunnelForwarder(
            config.SSH_HOST,
            ssh_username=config.SSH_USER,
            remote_bind_address=(config.PG_HOST, config.PG_PORT),
            local_bind_address=('127.0.0.1', 0),  # Random local port
        )
        self.tunnel.start()

        # Connect to postgres through tunnel
        self.conn = psycopg2.connect(
            host='127.0.0.1',
            port=self.tunnel.local_bind_port,
            database=config.PG_DATABASE,
            user=config.PG_USER,
            password=config.PG_PASSWORD or None,
        )
        self.conn.autocommit = False
        return self.conn

    def connect_via_docker_exec(self):
        """Alternative: run psql via docker exec over SSH (no tunnel needed)."""
        # This is useful for one-off commands
        pass

    def close(self):
        """Close connection and tunnel."""
        if self.conn:
            self.conn.close()
            self.conn = None
        if self.tunnel:
            self.tunnel.stop()
            self.tunnel = None

    @contextmanager
    def cursor(self):
        """Context manager for database cursor."""
        cur = self.conn.cursor()
        try:
            yield cur
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()


# Global connection instance
_db = None

def get_db() -> DatabaseConnection:
    """Get or create database connection."""
    global _db
    if _db is None:
        _db = DatabaseConnection()
        _db.connect_via_tunnel()
    return _db

def close_db():
    """Close global database connection."""
    global _db
    if _db:
        _db.close()
        _db = None

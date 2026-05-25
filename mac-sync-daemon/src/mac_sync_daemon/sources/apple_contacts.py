"""Sync Apple Contacts to bronze layer."""

import sqlite3
import logging
from pathlib import Path

from .. import config
from ..db import get_db

logger = logging.getLogger(__name__)


def find_contact_databases():
    """Find all AddressBook databases."""
    contacts_dir = config.CONTACTS_DIR
    if not contacts_dir.exists():
        return []

    dbs = []
    for source_dir in contacts_dir.iterdir():
        if source_dir.is_dir():
            db_path = source_dir / "AddressBook-v22.abcddb"
            if db_path.exists():
                dbs.append((source_dir.name, db_path))

    return dbs


def get_last_synced_id() -> int:
    """Get the last synced ROWID."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "SELECT last_sync_id FROM sync.sources WHERE name = 'apple_contacts'"
        )
        row = cur.fetchone()
        return row[0] if row else 0


def sync_contacts() -> int:
    """Sync contacts to bronze layer from all AddressBook sources."""
    logger.info("Syncing contacts...")

    databases = find_contact_databases()
    if not databases:
        logger.warning("No AddressBook databases found")
        return 0

    db = get_db()
    total_count = 0
    max_rowid = get_last_synced_id()

    for source_uuid, db_path in databases:
        logger.info(f"Syncing from source: {source_uuid}")

        try:
            sqlite_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            sqlite_conn.row_factory = sqlite3.Row

            # Sync contact records
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("""
                SELECT Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION,
                       ZJOBTITLE, ZNICKNAME
                FROM ZABCDRECORD
                WHERE Z_PK > ?
                ORDER BY Z_PK
                LIMIT ?
            """, (0, config.BATCH_SIZE))  # Always sync all from each source

            rows = sqlite_cur.fetchall()

            with db.cursor() as pg_cur:
                for row in rows:
                    # Insert contact
                    pg_cur.execute("""
                        INSERT INTO bronze.apple_contacts
                            (mac_rowid, source_uuid, first_name, last_name,
                             organization, job_title, nickname)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (mac_rowid, source_uuid) DO UPDATE SET
                            first_name = EXCLUDED.first_name,
                            last_name = EXCLUDED.last_name,
                            organization = EXCLUDED.organization,
                            synced_at = NOW()
                        RETURNING id
                    """, (
                        row['Z_PK'], source_uuid, row['ZFIRSTNAME'],
                        row['ZLASTNAME'], row['ZORGANIZATION'],
                        row['ZJOBTITLE'], row['ZNICKNAME']
                    ))
                    contact_id = pg_cur.fetchone()[0]

                    # Sync phone numbers for this contact
                    sqlite_cur2 = sqlite_conn.cursor()
                    sqlite_cur2.execute("""
                        SELECT ZFULLNUMBER, ZLABEL
                        FROM ZABCDPHONENUMBER
                        WHERE ZOWNER = ?
                    """, (row['Z_PK'],))

                    for phone in sqlite_cur2.fetchall():
                        if phone['ZFULLNUMBER']:
                            pg_cur.execute("""
                                INSERT INTO bronze.apple_contact_phones
                                    (contact_id, phone_number, label)
                                VALUES (%s, %s, %s)
                                ON CONFLICT DO NOTHING
                            """, (contact_id, phone['ZFULLNUMBER'], phone['ZLABEL']))

                    # Sync email addresses for this contact
                    sqlite_cur2.execute("""
                        SELECT ZADDRESS, ZLABEL
                        FROM ZABCDEMAILADDRESS
                        WHERE ZOWNER = ?
                    """, (row['Z_PK'],))

                    for email in sqlite_cur2.fetchall():
                        if email['ZADDRESS']:
                            pg_cur.execute("""
                                INSERT INTO bronze.apple_contact_emails
                                    (contact_id, email, label)
                                VALUES (%s, %s, %s)
                                ON CONFLICT DO NOTHING
                            """, (contact_id, email['ZADDRESS'], email['ZLABEL']))

                    max_rowid = max(max_rowid, row['Z_PK'])
                    total_count += 1

            sqlite_conn.close()

        except sqlite3.Error as e:
            logger.warning(f"Error reading {db_path}: {e}")
            continue

    # Update sync state
    if total_count > 0:
        with db.cursor() as pg_cur:
            pg_cur.execute("""
                UPDATE sync.sources
                SET last_sync_id = %s,
                    last_sync_count = %s,
                    last_sync_at = NOW(),
                    sync_status = 'success',
                    sync_error = NULL,
                    updated_at = NOW()
                WHERE name = 'apple_contacts'
            """, (max_rowid, total_count))

    logger.info(f"Synced {total_count} contacts total")
    return total_count

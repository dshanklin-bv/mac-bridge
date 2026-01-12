"""
Sync contacts to bronze.apple_contacts.
Reads from ~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb
Uses watermarks for incremental sync.
"""

import sqlite3
import logging
from pathlib import Path

from psycopg2.extras import execute_values

from tosh.utils.db import get_connection
from tosh.utils.watermark import get_watermark, set_watermark

logger = logging.getLogger(__name__)

WATERMARK_COLUMN = "ZMODIFICATIONDATE"  # Apple epoch seconds, catches inserts AND updates

ADDRESSBOOK_DIR = Path.home() / "Library" / "Application Support" / "AddressBook" / "Sources"
BATCH_SIZE = 1000


def find_addressbook_dbs() -> list:
    """Find all AddressBook database files."""
    dbs = []
    if ADDRESSBOOK_DIR.exists():
        for source_dir in ADDRESSBOOK_DIR.iterdir():
            if source_dir.is_dir():
                db_path = source_dir / "AddressBook-v22.abcddb"
                if db_path.exists():
                    dbs.append((source_dir.name, db_path))
    return dbs


def sync() -> int:
    """
    Sync contacts to bronze layer using batch inserts with watermarks.

    Returns:
        Number of records synced.
    """
    # Get current watermark for incremental sync
    watermark = get_watermark("contacts")
    if watermark:
        logger.info(f"Using watermark: {WATERMARK_COLUMN} > {watermark}")
    else:
        logger.info("No watermark found, doing full sync")

    logger.info("Finding AddressBook databases...")

    dbs = find_addressbook_dbs()
    if not dbs:
        logger.warning("No AddressBook databases found")
        return 0

    logger.info(f"Found {len(dbs)} AddressBook source(s)")

    all_contacts = []
    all_phones = []
    all_emails = []
    max_mod_date = None

    for source_uuid, db_path in dbs:
        logger.info(f"Reading source: {source_uuid}")

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Get contacts (with watermark filter if set)
            if watermark:
                cur.execute("""
                    SELECT
                        Z_PK as rowid,
                        ZFIRSTNAME as first_name,
                        ZLASTNAME as last_name,
                        ZORGANIZATION as organization,
                        ZJOBTITLE as job_title,
                        ZNICKNAME as nickname,
                        ZMODIFICATIONDATE as mod_date
                    FROM ZABCDRECORD
                    WHERE (ZFIRSTNAME IS NOT NULL OR ZLASTNAME IS NOT NULL)
                      AND ZMODIFICATIONDATE > ?
                    ORDER BY ZMODIFICATIONDATE ASC
                """, (float(watermark),))
            else:
                cur.execute("""
                    SELECT
                        Z_PK as rowid,
                        ZFIRSTNAME as first_name,
                        ZLASTNAME as last_name,
                        ZORGANIZATION as organization,
                        ZJOBTITLE as job_title,
                        ZNICKNAME as nickname,
                        ZMODIFICATIONDATE as mod_date
                    FROM ZABCDRECORD
                    WHERE ZFIRSTNAME IS NOT NULL OR ZLASTNAME IS NOT NULL
                    ORDER BY ZMODIFICATIONDATE ASC
                """)

            contacts_map = {}  # rowid -> (source_uuid, contact_data)
            for row in cur.fetchall():
                contacts_map[row['rowid']] = (source_uuid, row)
                all_contacts.append((
                    row['rowid'], source_uuid, row['first_name'], row['last_name'],
                    row['organization'], row['job_title'], row['nickname']
                ))
                # Track max modification date for watermark
                if row['mod_date'] and (max_mod_date is None or row['mod_date'] > max_mod_date):
                    max_mod_date = row['mod_date']

            # Get phone numbers
            cur.execute("""
                SELECT ZOWNER as contact_id, ZFULLNUMBER as phone_number, ZLABEL as label
                FROM ZABCDPHONENUMBER
                WHERE ZFULLNUMBER IS NOT NULL
            """)
            for row in cur.fetchall():
                if row['contact_id'] in contacts_map:
                    all_phones.append((row['contact_id'], source_uuid, row['phone_number'], row['label']))

            # Get emails
            cur.execute("""
                SELECT ZOWNER as contact_id, ZADDRESS as email, ZLABEL as label
                FROM ZABCDEMAILADDRESS
                WHERE ZADDRESS IS NOT NULL
            """)
            for row in cur.fetchall():
                if row['contact_id'] in contacts_map:
                    all_emails.append((row['contact_id'], source_uuid, row['email'], row['label']))

            conn.close()

        except Exception as e:
            logger.error(f"Failed to read source {source_uuid}: {e}")
            continue

    logger.info(f"Found {len(all_contacts)} contacts to sync, {len(all_phones)} phones, {len(all_emails)} emails")

    if not all_contacts:
        return 0

    # Sync to bronze with batch inserts
    db_conn = get_connection()
    try:
        with db_conn.cursor() as cur:
            # First, insert/update contacts and get their IDs
            # We need to do this in a way that maps (mac_rowid, source_uuid) -> id

            # Upsert contacts
            logger.info("Syncing contacts...")
            sql = """
                INSERT INTO bronze.apple_contacts (
                    mac_rowid, source_uuid, first_name, last_name,
                    organization, job_title, nickname
                )
                VALUES %s
                ON CONFLICT (mac_rowid, source_uuid) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    organization = EXCLUDED.organization,
                    job_title = EXCLUDED.job_title,
                    nickname = EXCLUDED.nickname,
                    synced_at = NOW()
            """
            execute_values(cur, sql, all_contacts, page_size=BATCH_SIZE)

            # Get contact ID mapping
            cur.execute("""
                SELECT id, mac_rowid, source_uuid FROM bronze.apple_contacts
            """)
            contact_id_map = {(row[1], row[2]): row[0] for row in cur.fetchall()}

            # Map phones to contact IDs
            phones_with_ids = []
            for mac_rowid, source_uuid, phone, label in all_phones:
                contact_id = contact_id_map.get((mac_rowid, source_uuid))
                if contact_id:
                    phones_with_ids.append((contact_id, phone, label))

            # Upsert phones
            if phones_with_ids:
                logger.info(f"Syncing {len(phones_with_ids)} phone numbers...")
                sql = """
                    INSERT INTO bronze.apple_contact_phones (contact_id, phone_number, label)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                execute_values(cur, sql, phones_with_ids, page_size=BATCH_SIZE)

            # Map emails to contact IDs
            emails_with_ids = []
            for mac_rowid, source_uuid, email, label in all_emails:
                contact_id = contact_id_map.get((mac_rowid, source_uuid))
                if contact_id:
                    emails_with_ids.append((contact_id, email, label))

            # Upsert emails
            if emails_with_ids:
                logger.info(f"Syncing {len(emails_with_ids)} email addresses...")
                sql = """
                    INSERT INTO bronze.apple_contact_emails (contact_id, email, label)
                    VALUES %s
                    ON CONFLICT DO NOTHING
                """
                execute_values(cur, sql, emails_with_ids, page_size=BATCH_SIZE)

        db_conn.commit()
        logger.info(f"Synced {len(all_contacts)} contacts to bronze")

        # Update watermark AFTER successful commit
        if max_mod_date is not None:
            set_watermark("contacts", WATERMARK_COLUMN, str(max_mod_date), len(all_contacts))

        return len(all_contacts)

    except Exception:
        db_conn.rollback()
        raise
    finally:
        db_conn.close()

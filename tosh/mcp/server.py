#!/usr/bin/env python3
"""
Tosh MCP Server

Exposes Mac sync data to Claude via Model Context Protocol.
Run with: python -m tosh.mcp.server
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for tosh imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastmcp import FastMCP

from tosh.utils.db import get_connection, get_argus_connection

mcp = FastMCP(
    name="tosh",
    instructions="Tosh MCP - Access Mac sync data (photos, messages, contacts) and agent messaging."
)


# =============================================================================
# Photo Tools
# =============================================================================

@mcp.tool()
def photo_stats() -> str:
    """Get current photo sync statistics - synced, pending, iCloud remaining."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE sync_status = 'synced') as synced,
                    COUNT(*) FILTER (WHERE sync_status = 'pending') as pending,
                    COUNT(*) FILTER (WHERE sync_status = 'in_cloud') as in_cloud,
                    COUNT(*) FILTER (WHERE sync_status = 'missing') as missing
                FROM bronze.apple_photos
            """)
            row = cur.fetchone()
            total, synced, pending, in_cloud, missing = row

            return json.dumps({
                "total": total,
                "synced": synced,
                "pending": pending,
                "in_cloud": in_cloud,
                "missing": missing,
                "percent_complete": round(synced / total * 100, 1) if total > 0 else 0
            }, indent=2)
    finally:
        conn.close()


@mcp.tool()
def photo_progress() -> str:
    """Get photo sync progress - date range covered, today's sync stats."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Overall range synced
            cur.execute("""
                SELECT MIN(date_created), MAX(date_created)
                FROM bronze.apple_photos
                WHERE sync_status = 'synced'
            """)
            oldest_all, newest_all = cur.fetchone()

            # Today's range
            cur.execute("""
                SELECT
                    MIN(date_created),
                    MAX(date_created),
                    COUNT(*)
                FROM bronze.apple_photos
                WHERE sync_status = 'synced'
                  AND synced_at::date = CURRENT_DATE
            """)
            oldest_today, newest_today, count_today = cur.fetchone()

            return json.dumps({
                "total_range": {
                    "oldest": str(oldest_all) if oldest_all else None,
                    "newest": str(newest_all) if newest_all else None
                },
                "today": {
                    "oldest": str(oldest_today) if oldest_today else None,
                    "newest": str(newest_today) if newest_today else None,
                    "count": count_today or 0
                }
            }, indent=2)
    finally:
        conn.close()


@mcp.tool()
def photo_breakdown(by: str = "year") -> str:
    """
    Get remaining iCloud photos breakdown.

    Args:
        by: Group by 'year' or 'month'
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if by == "month":
                cur.execute("""
                    SELECT
                        SUBSTRING(date_created, 1, 7) as period,
                        COUNT(*) as remaining
                    FROM bronze.apple_photos
                    WHERE sync_status = 'in_cloud'
                      AND date_created IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1 DESC
                """)
            else:
                cur.execute("""
                    SELECT
                        SUBSTRING(date_created, 1, 4) as period,
                        COUNT(*) as remaining
                    FROM bronze.apple_photos
                    WHERE sync_status = 'in_cloud'
                      AND date_created IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1 DESC
                """)

            rows = cur.fetchall()
            result = {row[0]: row[1] for row in rows}
            result["_total"] = sum(r[1] for r in rows)

            return json.dumps(result, indent=2)
    finally:
        conn.close()


# =============================================================================
# Agent Messaging Tools
# =============================================================================

@mcp.tool()
def send_to_reeves(subject: str, body: str, priority: str = "normal") -> str:
    """
    Send a message to reeves agent.

    Args:
        subject: Message subject
        body: Message body (markdown supported)
        priority: Priority level (low, normal, high, urgent)
    """
    conn = get_argus_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO argus.agent_messages (
                    id, from_agent, to_agent, subject, body,
                    priority, message_type, status, created_at
                ) VALUES (
                    gen_random_uuid(), 'tosh', 'reeves', %s, %s,
                    %s, 'message', 'sent', NOW()
                )
                RETURNING id
            """, (subject, body, priority))
            msg_id = cur.fetchone()[0]
        conn.commit()
        return json.dumps({"status": "sent", "message_id": str(msg_id)})
    finally:
        conn.close()


@mcp.tool()
def read_from_reeves(limit: int = 5) -> str:
    """
    Read recent messages from reeves.

    Args:
        limit: Number of messages to retrieve (default 5)
    """
    conn = get_argus_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT subject, body, created_at, message_type, priority
                FROM argus.agent_messages
                WHERE to_agent = 'tosh'
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))

            messages = []
            for row in cur.fetchall():
                messages.append({
                    "subject": row[0],
                    "body": row[1],
                    "created_at": str(row[2]),
                    "type": row[3],
                    "priority": row[4]
                })

            return json.dumps({"count": len(messages), "messages": messages}, indent=2)
    finally:
        conn.close()


# =============================================================================
# Message Search Tools
# =============================================================================

@mcp.tool()
def search_messages(contact: str, limit: int = 20) -> str:
    """
    Search iMessages by contact name.

    Args:
        contact: Contact name to search for (first or last name)
        limit: Max messages to return (default 20)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Find contact's phone numbers
            cur.execute("""
                SELECT DISTINCT p.phone_number
                FROM bronze.apple_contacts c
                JOIN bronze.apple_contact_phones p ON c.id = p.contact_id
                WHERE LOWER(c.first_name) LIKE LOWER(%s)
                   OR LOWER(c.last_name) LIKE LOWER(%s)
            """, (f"%{contact}%", f"%{contact}%"))

            phones = [row[0] for row in cur.fetchall()]
            if not phones:
                return json.dumps({"error": f"No contact found matching '{contact}'"})

            # Extract digits for matching
            digits = [''.join(filter(str.isdigit, p))[-10:] for p in phones]

            # Find handle IDs
            like_patterns = [f"%{d}%" for d in digits if d]
            if not like_patterns:
                return json.dumps({"error": "No valid phone numbers found"})

            cur.execute("""
                SELECT id FROM bronze.apple_handles
                WHERE """ + " OR ".join(["identifier LIKE %s"] * len(like_patterns)),
                like_patterns
            )
            handle_ids = [row[0] for row in cur.fetchall()]

            if not handle_ids:
                return json.dumps({"error": "No message handles found for contact"})

            # Get messages
            cur.execute("""
                SELECT m.text, m.is_from_me, m.date_apple
                FROM bronze.apple_messages m
                WHERE m.handle_id = ANY(%s)
                  AND m.text IS NOT NULL
                  AND m.text != ''
                ORDER BY m.date_apple DESC
                LIMIT %s
            """, (handle_ids, limit))

            messages = []
            for text, is_from_me, date in cur.fetchall():
                messages.append({
                    "from": "me" if is_from_me else contact,
                    "text": text[:500],  # Truncate long messages
                    "date": date
                })

            return json.dumps({
                "contact": contact,
                "count": len(messages),
                "messages": messages
            }, indent=2)
    finally:
        conn.close()


@mcp.tool()
def search_contacts(query: str) -> str:
    """
    Search contacts by name.

    Args:
        query: Name to search for
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT c.first_name, c.last_name, p.phone_number, e.email
                FROM bronze.apple_contacts c
                LEFT JOIN bronze.apple_contact_phones p ON c.id = p.contact_id
                LEFT JOIN bronze.apple_contact_emails e ON c.id = e.contact_id
                WHERE LOWER(c.first_name) LIKE LOWER(%s)
                   OR LOWER(c.last_name) LIKE LOWER(%s)
                LIMIT 20
            """, (f"%{query}%", f"%{query}%"))

            contacts = {}
            for first, last, phone, email in cur.fetchall():
                name = f"{first or ''} {last or ''}".strip()
                if name not in contacts:
                    contacts[name] = {"phones": [], "emails": []}
                if phone and phone not in contacts[name]["phones"]:
                    contacts[name]["phones"].append(phone)
                if email and email not in contacts[name]["emails"]:
                    contacts[name]["emails"].append(email)

            return json.dumps(contacts, indent=2)
    finally:
        conn.close()


# =============================================================================
# Daemon Status Tools
# =============================================================================

@mcp.tool()
def daemon_status() -> str:
    """Get tosh daemon status - running, last cycle, recent activity."""
    import subprocess

    result = {
        "launchd_loaded": False,
        "last_cycle": None,
        "recent_logs": []
    }

    # Check if daemon is loaded
    try:
        proc = subprocess.run(
            ["launchctl", "list", "com.tosh.daemon"],
            capture_output=True, text=True
        )
        result["launchd_loaded"] = proc.returncode == 0
    except Exception:
        pass

    # Get recent log entries
    log_path = Path.home() / ".tosh/logs/daemon.log"
    if log_path.exists():
        lines = log_path.read_text().strip().split('\n')[-20:]
        result["recent_logs"] = lines

        # Find last complete cycle
        for line in reversed(lines):
            if "daemon complete" in line:
                result["last_cycle"] = line
                break

    return json.dumps(result, indent=2)


# =============================================================================
# Documentation Tools
# =============================================================================

@mcp.tool()
def devlog_add(content: str, title: str = "", category: str = "general") -> str:
    """
    Add a note to the tosh devlog.

    Args:
        content: The note content
        title: Short title for the entry (optional)
        category: Category (general, schema, bug, feature, learning)
    """
    devlog_path = Path(__file__).parent.parent / "docs" / "devlog.md"
    devlog_path.parent.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"## [{category}] {timestamp}"
    if title:
        header += f" - {title}"
    entry = f"\n{header}\n\n{content}\n"

    with open(devlog_path, "a") as f:
        f.write(entry)

    return json.dumps({"status": "added", "file": str(devlog_path)})


def _parse_devlog_entries() -> list[dict]:
    """Parse devlog into structured entries with IDs."""
    devlog_path = Path(__file__).parent.parent / "docs" / "devlog.md"

    if not devlog_path.exists():
        return []

    content = devlog_path.read_text()
    entries = []
    current_lines = []
    current_header = None

    for line in content.split('\n'):
        if line.startswith('## ['):
            if current_header and current_lines:
                entries.append({
                    "header": current_header,
                    "content": '\n'.join(current_lines).strip()
                })
            current_header = line
            current_lines = []
        elif current_header:
            current_lines.append(line)

    if current_header:
        entries.append({
            "header": current_header,
            "content": '\n'.join(current_lines).strip()
        })

    # Add IDs (index from start of file - stable)
    for i, entry in enumerate(entries):
        entry["id"] = i

    return entries


@mcp.tool()
def devlog_list(limit: int = 10) -> str:
    """
    List recent devlog entries (headers + IDs). Use devlog_read to get full content.

    Args:
        limit: Number of entries to list (default 10)
    """
    entries = _parse_devlog_entries()

    if not entries:
        return json.dumps({"error": "No devlog found"})

    # Most recent first
    recent = entries[-limit:] if len(entries) > limit else entries
    recent = list(reversed(recent))

    return json.dumps({
        "total_entries": len(entries),
        "showing": len(recent),
        "entries": [{"id": e["id"], "header": e["header"]} for e in recent]
    }, indent=2)


@mcp.tool()
def devlog_read(entry_id: int) -> str:
    """
    Read a specific devlog entry by ID.

    Args:
        entry_id: Entry ID to read (get IDs from devlog_list)
    """
    entries = _parse_devlog_entries()

    if not entries:
        return json.dumps({"error": "No devlog found"})

    if 0 <= entry_id < len(entries):
        entry = entries[entry_id]
        return json.dumps({
            "id": entry["id"],
            "header": entry["header"],
            "content": entry["content"]
        }, indent=2)
    else:
        return json.dumps({"error": f"Entry ID {entry_id} not found (0-{len(entries)-1} valid)"})


@mcp.tool()
def devlog_search(query: str) -> str:
    """
    Search devlog entries for a keyword. Returns full content of matches.

    Args:
        query: Search term to find in devlog
    """
    entries = _parse_devlog_entries()

    if not entries:
        return json.dumps({"error": "No devlog found"})

    # Search for matches - return full content
    matches = []
    for entry in entries:
        full_text = entry["header"] + "\n" + entry["content"]
        if query.lower() in full_text.lower():
            matches.append({
                "id": entry["id"],
                "header": entry["header"],
                "content": entry["content"]
            })

    return json.dumps({
        "query": query,
        "total_entries": len(entries),
        "matches": len(matches),
        "results": matches
    }, indent=2)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    mcp.run()

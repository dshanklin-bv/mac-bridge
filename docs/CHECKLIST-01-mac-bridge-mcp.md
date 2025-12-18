---
project: mac-bridge
type: checklist
phase: 1
component: mac-bridge-mcp
date: 2025-12-18
status: not-started
---

# CHECKLIST 01: mac-bridge-mcp (Local MCP Server)

## Overview

Build a unified MCP server for Claude Code that provides access to Messages, Calls, and Contacts with human-in-the-loop safety for sends.

**Estimated Time:** 4-6 hours
**Dependencies:** None (local only)
**Output:** Working MCP server installable via `uvx`

---

## Pre-Flight Checks

Before starting, verify:

- [ ] **Check 0.1**: Python 3.11+ installed
  ```bash
  python3 --version
  # Expected: Python 3.11.x or higher
  ```

- [ ] **Check 0.2**: uv installed
  ```bash
  uv --version
  # Expected: uv 0.x.x
  ```

- [ ] **Check 0.3**: Full Disk Access granted to Terminal/Claude Code
  ```bash
  sqlite3 ~/Library/Messages/chat.db "SELECT COUNT(*) FROM message LIMIT 1;"
  # Expected: A number (not a permission error)
  ```

- [ ] **Check 0.4**: Can query call history
  ```bash
  sqlite3 ~/Library/Application\ Support/CallHistoryDB/CallHistory.storedata "SELECT COUNT(*) FROM ZCALLRECORD;"
  # Expected: A number
  ```

- [ ] **Check 0.5**: Can query contacts
  ```bash
  sqlite3 ~/Library/Application\ Support/AddressBook/Sources/*/AddressBook-v22.abcddb "SELECT COUNT(*) FROM ZABCDRECORD;" 2>/dev/null | head -1
  # Expected: A number
  ```

**STOP if any check fails. Fix permissions first.**

---

## Section 1: Repository Setup

### 1.1 Create GitHub Repository

- [ ] **Task 1.1.1**: Create repository on GitHub
  ```bash
  gh repo create dshanklin-bv/mac-bridge --public --description "Unified MCP server for macOS Messages, Calls, and Contacts"
  ```
  **Record:** Repository URL: _________________

- [ ] **Task 1.1.2**: Clone repository locally
  ```bash
  cd ~/repos
  git clone git@github.com:dshanklin-bv/mac-bridge.git
  cd mac-bridge
  ```

- [ ] **Task 1.1.3**: Create directory structure
  ```bash
  mkdir -p mac-bridge-mcp/src/mac_bridge_mcp
  mkdir -p mac-bridge-mcp/tests
  mkdir -p docs
  touch mac-bridge-mcp/src/mac_bridge_mcp/__init__.py
  touch README.md
  ```

### 1.2 Initialize Python Project

- [ ] **Task 1.2.1**: Create `pyproject.toml`
  ```toml
  # mac-bridge-mcp/pyproject.toml
  [project]
  name = "mac-bridge-mcp"
  version = "0.1.0"
  description = "Unified MCP server for macOS Messages, Calls, and Contacts"
  readme = "README.md"
  requires-python = ">=3.11"
  dependencies = [
      "mcp>=1.0.0",
      "thefuzz>=0.22.1",
  ]

  [project.scripts]
  mac-bridge-mcp = "mac_bridge_mcp.server:run_server"

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [tool.hatch.build.targets.wheel]
  packages = ["src/mac_bridge_mcp"]
  ```

- [ ] **Task 1.2.2**: Create virtual environment and install dependencies
  ```bash
  cd mac-bridge-mcp
  uv venv
  source .venv/bin/activate
  uv pip install -e .
  ```
  **Test:** `python -c "import mac_bridge_mcp"` should not error

---

## Section 2: Core Database Access Layer

### 2.1 Database Utilities (`db.py`)

- [ ] **Task 2.1.1**: Create database utilities module
  ```python
  # src/mac_bridge_mcp/db.py
  """Database utilities for accessing macOS SQLite databases."""

  import os
  import glob
  import sqlite3
  from typing import Any, Dict, List, Optional

  # Database paths
  MESSAGES_DB = os.path.expanduser("~/Library/Messages/chat.db")
  CALLS_DB = os.path.expanduser("~/Library/Application Support/CallHistoryDB/CallHistory.storedata")
  CONTACTS_PATTERN = os.path.expanduser("~/Library/Application Support/AddressBook/Sources/*/AddressBook-v22.abcddb")

  def query_db(db_path: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
      """Execute a query and return results as list of dicts."""
      # Implementation here
      pass

  def query_messages_db(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
      """Query the Messages database."""
      return query_db(MESSAGES_DB, query, params)

  def query_calls_db(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
      """Query the Call History database."""
      return query_db(CALLS_DB, query, params)

  def query_contacts_db(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
      """Query all AddressBook databases and combine results."""
      # Implementation here
      pass
  ```

- [ ] **Task 2.1.2**: Implement `query_db` function with error handling
  - Handle missing database file
  - Handle permission denied
  - Handle locked database
  - Return helpful error messages

- [ ] **Task 2.1.3**: Write unit tests for database utilities
  ```python
  # tests/test_db.py
  def test_query_messages_db_accessible():
      """Test that messages DB is accessible."""
      result = query_messages_db("SELECT COUNT(*) as count FROM message")
      assert "error" not in result[0] or result[0].get("count") is not None

  def test_query_calls_db_accessible():
      """Test that calls DB is accessible."""
      result = query_calls_db("SELECT COUNT(*) as count FROM ZCALLRECORD")
      assert "error" not in result[0] or result[0].get("count") is not None

  def test_query_contacts_db_accessible():
      """Test that contacts DB is accessible."""
      result = query_contacts_db("SELECT COUNT(*) as count FROM ZABCDRECORD")
      assert len(result) > 0
  ```

- [ ] **Test 2.1**: Run database tests
  ```bash
  pytest tests/test_db.py -v
  ```
  **Record:** All tests pass? [ ] Yes [ ] No
  **If No, record errors:** _________________

---

## Section 3: Contacts Module

### 3.1 Contact Resolution (`contacts.py`)

- [ ] **Task 3.1.1**: Create contacts module with unified contact lookup
  ```python
  # src/mac_bridge_mcp/contacts.py
  """Unified contact resolution from multiple sources."""

  from typing import Dict, List, Optional, Any
  from thefuzz import fuzz
  from .db import query_contacts_db

  # Cache
  _CONTACTS_CACHE: Optional[Dict[str, str]] = None
  _CACHE_TIME: float = 0
  CACHE_TTL: int = 300  # 5 minutes

  def normalize_phone(phone: str) -> str:
      """Normalize phone number to digits only."""
      return ''.join(c for c in phone if c.isdigit())

  def get_all_contacts() -> Dict[str, str]:
      """Get all contacts as {normalized_phone: name} dict."""
      pass

  def find_contact_by_phone(phone: str) -> Optional[str]:
      """Find contact name by phone number."""
      pass

  def find_contact_by_name(name: str, threshold: float = 0.6) -> List[Dict[str, Any]]:
      """Fuzzy search contacts by name."""
      pass

  def resolve_identifier(identifier: str) -> Dict[str, Any]:
      """Resolve phone/email/name to a contact."""
      pass
  ```

- [ ] **Task 3.1.2**: Implement contact caching with TTL

- [ ] **Task 3.1.3**: Implement fuzzy name matching
  - Use `thefuzz.fuzz.WRatio` for scoring
  - Return top 10 matches above threshold
  - Include match score in results

- [ ] **Task 3.1.4**: Write unit tests for contacts
  ```python
  # tests/test_contacts.py
  def test_normalize_phone():
      assert normalize_phone("+1 (512) 784-1141") == "15127841141"
      assert normalize_phone("512-784-1141") == "5127841141"

  def test_get_all_contacts_returns_dict():
      contacts = get_all_contacts()
      assert isinstance(contacts, dict)
      assert len(contacts) > 0  # Assuming contacts exist

  def test_find_contact_by_name_fuzzy():
      # This depends on actual contacts
      results = find_contact_by_name("Taylor")
      assert isinstance(results, list)
  ```

- [ ] **Test 3.1**: Run contacts tests
  ```bash
  pytest tests/test_contacts.py -v
  ```
  **Record:** All tests pass? [ ] Yes [ ] No

---

## Section 4: Call History Module

### 4.1 Call History Access (`calls.py`)

- [ ] **Task 4.1.1**: Create calls module
  ```python
  # src/mac_bridge_mcp/calls.py
  """Call history access with contact resolution."""

  from datetime import datetime, timedelta, timezone
  from typing import List, Dict, Any, Optional
  from .db import query_calls_db
  from .contacts import find_contact_by_phone

  # Apple epoch offset (2001-01-01 to Unix epoch)
  APPLE_EPOCH_OFFSET = 978307200

  def get_recent_calls(hours: int = 168) -> List[Dict[str, Any]]:
      """Get recent calls with contact resolution."""
      pass

  def get_calls_with_contact(identifier: str, hours: int = 168) -> List[Dict[str, Any]]:
      """Get calls with a specific contact."""
      pass

  def get_call_stats() -> Dict[str, Any]:
      """Get aggregate call statistics."""
      pass
  ```

- [ ] **Task 4.1.2**: Implement Apple timestamp conversion
  ```python
  def apple_timestamp_to_datetime(timestamp: int) -> datetime:
      """Convert Apple Core Data timestamp to datetime."""
      return datetime.fromtimestamp(timestamp + APPLE_EPOCH_OFFSET, tz=timezone.utc)
  ```

- [ ] **Task 4.1.3**: Implement `get_recent_calls` with:
  - Contact name resolution
  - Direction (incoming/outgoing)
  - Status (answered/missed/declined)
  - Duration in minutes
  - Formatted timestamp

- [ ] **Task 4.1.4**: Write unit tests for calls
  ```python
  # tests/test_calls.py
  def test_apple_timestamp_conversion():
      # Dec 15, 2025 approximately
      ts = 787449600  # Seconds since Apple epoch
      dt = apple_timestamp_to_datetime(ts)
      assert dt.year == 2025

  def test_get_recent_calls_format():
      calls = get_recent_calls(hours=24)
      assert isinstance(calls, list)
      if calls:
          call = calls[0]
          assert "contact" in call or "number" in call
          assert "direction" in call
          assert "timestamp" in call
  ```

- [ ] **Test 4.1**: Run calls tests
  ```bash
  pytest tests/test_calls.py -v
  ```
  **Record:** All tests pass? [ ] Yes [ ] No

---

## Section 5: Messages Module

### 5.1 Messages Access (`messages.py`)

- [ ] **Task 5.1.1**: Port messages functionality from `mac-messages-mcp`
  - Copy and adapt `get_recent_messages`
  - Copy and adapt `send_message` (but DO NOT implement send yet)
  - Copy contact resolution helpers

- [ ] **Task 5.1.2**: Adapt for unified contacts module
  - Use `contacts.find_contact_by_phone` instead of inline lookup
  - Use `contacts.resolve_identifier` for recipient resolution

- [ ] **Task 5.1.3**: Add conversation thread support
  ```python
  def get_conversation(contact: str, hours: int = 168) -> Dict[str, Any]:
      """Get conversation thread with a contact."""
      return {
          "contact": contact_name,
          "messages": [...],
          "message_count": len(messages),
          "last_message": last_msg_time,
      }
  ```

- [ ] **Task 5.1.4**: Write unit tests for messages
  ```python
  # tests/test_messages.py
  def test_get_recent_messages_format():
      messages = get_recent_messages(hours=24)
      assert isinstance(messages, str)  # Formatted string
      # Or if returning structured data:
      # assert isinstance(messages, list)
  ```

- [ ] **Test 5.1**: Run messages tests
  ```bash
  pytest tests/test_messages.py -v
  ```
  **Record:** All tests pass? [ ] Yes [ ] No

---

## Section 6: Human-in-the-Loop Confirmation

### 6.1 Confirmation Dialog (`confirmation.py`)

- [ ] **Task 6.1.1**: Create confirmation module
  ```python
  # src/mac_bridge_mcp/confirmation.py
  """Human-in-the-loop confirmation for sensitive actions."""

  import subprocess
  from typing import Tuple

  def show_send_confirmation(recipient: str, message: str) -> Tuple[bool, str]:
      """
      Show macOS dialog to confirm message send.

      Returns:
          (approved, button_clicked)
      """
      # Escape quotes for AppleScript
      safe_recipient = recipient.replace('"', '\\"')
      safe_message = message.replace('"', '\\"').replace('\n', '\\n')

      script = f'''
      display dialog "Send message to {safe_recipient}?" & return & return & "{safe_message}" ¬
          buttons {{"Cancel", "Send"}} default button "Send" ¬
          with title "Mac Bridge - Confirm Send" ¬
          with icon caution
      '''

      try:
          result = subprocess.run(
              ['osascript', '-e', script],
              capture_output=True,
              text=True,
              timeout=60  # 1 minute timeout
          )

          if result.returncode == 0:
              return True, "Send"
          else:
              return False, "Cancel"
      except subprocess.TimeoutExpired:
          return False, "Timeout"
      except Exception as e:
          return False, f"Error: {str(e)}"
  ```

- [ ] **Task 6.1.2**: Write manual test for confirmation dialog
  ```python
  # tests/test_confirmation_manual.py
  """
  MANUAL TEST - Run interactively to verify dialog works.

  Run with: python tests/test_confirmation_manual.py
  """
  from mac_bridge_mcp.confirmation import show_send_confirmation

  if __name__ == "__main__":
      print("Testing confirmation dialog...")
      print("A dialog should appear. Click 'Send' to test approval.")

      approved, button = show_send_confirmation(
          "Test Recipient",
          "This is a test message.\nWith multiple lines."
      )

      print(f"Result: approved={approved}, button={button}")

      if approved:
          print("SUCCESS: Dialog approval works")
      else:
          print("INFO: Dialog was cancelled (this is also valid)")
  ```

- [ ] **Test 6.1**: Run manual confirmation test
  ```bash
  python tests/test_confirmation_manual.py
  ```
  **Record:**
  - Dialog appeared? [ ] Yes [ ] No
  - "Send" button worked? [ ] Yes [ ] No
  - "Cancel" button worked? [ ] Yes [ ] No
  - Dialog timeout handled? [ ] Yes [ ] No

---

## Section 7: Proactive Insights

### 7.1 Insights Engine (`insights.py`)

- [ ] **Task 7.1.1**: Create insights module
  ```python
  # src/mac_bridge_mcp/insights.py
  """Proactive insights from communication data."""

  from typing import List, Dict, Any
  from .messages import get_recent_messages, query_messages_db
  from .calls import get_recent_calls

  def get_unanswered_messages(hours: int = 48) -> List[Dict[str, Any]]:
      """
      Find messages received but not replied to.

      Returns messages where:
      - Received from someone (is_from_me = 0)
      - No subsequent message to that person (is_from_me = 1)
      """
      pass

  def get_unreturned_calls(hours: int = 48) -> List[Dict[str, Any]]:
      """
      Find missed calls not returned.

      Returns calls where:
      - Incoming and not answered
      - No subsequent outgoing call to same number
      """
      pass

  def get_communication_summary(hours: int = 24) -> Dict[str, Any]:
      """
      Get summary of recent communication activity.

      Returns:
          {
              "messages_received": count,
              "messages_sent": count,
              "calls_received": count,
              "calls_made": count,
              "missed_calls": count,
              "unanswered_messages": [...],
              "unreturned_calls": [...],
          }
      """
      pass
  ```

- [ ] **Task 7.1.2**: Implement unanswered messages detection
  - Query messages in time window
  - Group by handle_id
  - Find handles where last message is incoming

- [ ] **Task 7.1.3**: Implement unreturned calls detection
  - Query missed/unanswered calls
  - Check for subsequent outgoing calls to same number
  - Exclude if outgoing call exists after missed call

- [ ] **Task 7.1.4**: Write unit tests for insights
  ```python
  # tests/test_insights.py
  def test_communication_summary_format():
      summary = get_communication_summary(hours=24)
      assert "messages_received" in summary
      assert "calls_received" in summary
      assert "unanswered_messages" in summary
  ```

- [ ] **Test 7.1**: Run insights tests
  ```bash
  pytest tests/test_insights.py -v
  ```
  **Record:** All tests pass? [ ] Yes [ ] No

---

## Section 8: MCP Server

### 8.1 FastMCP Server (`server.py`)

- [ ] **Task 8.1.1**: Create MCP server with all tools
  ```python
  # src/mac_bridge_mcp/server.py
  """Mac Bridge MCP Server."""

  import logging
  import sys
  from mcp.server.fastmcp import Context, FastMCP

  from .messages import get_recent_messages, send_message_with_confirmation
  from .calls import get_recent_calls, get_call_stats
  from .contacts import find_contact_by_name, get_all_contacts
  from .insights import get_communication_summary, get_unanswered_messages
  from .confirmation import show_send_confirmation

  logging.basicConfig(level=logging.INFO, stream=sys.stderr)
  logger = logging.getLogger("mac_bridge_mcp")

  mcp = FastMCP("MacBridge")

  # === MESSAGE TOOLS ===

  @mcp.tool()
  def get_messages(ctx: Context, hours: int = 24, contact: str = None) -> str:
      """Get recent messages, optionally filtered by contact."""
      pass

  @mcp.tool()
  def send_message(ctx: Context, recipient: str, message: str) -> str:
      """
      Send a message with human confirmation.

      IMPORTANT: This will show a confirmation dialog to the user.
      The message will NOT be sent unless the user clicks "Send".
      """
      # 1. Resolve recipient
      # 2. Show confirmation dialog
      # 3. If approved, send message
      # 4. Return result
      pass

  # === CALL TOOLS ===

  @mcp.tool()
  def get_calls(ctx: Context, hours: int = 168, contact: str = None) -> str:
      """Get recent call history, optionally filtered by contact."""
      pass

  @mcp.tool()
  def get_call_statistics(ctx: Context) -> str:
      """Get aggregate call statistics."""
      pass

  # === CONTACT TOOLS ===

  @mcp.tool()
  def search_contacts(ctx: Context, query: str) -> str:
      """Search contacts by name using fuzzy matching."""
      pass

  @mcp.tool()
  def list_contacts(ctx: Context, limit: int = 50) -> str:
      """List contacts from address book."""
      pass

  # === INSIGHT TOOLS ===

  @mcp.tool()
  def get_insights(ctx: Context, hours: int = 24) -> str:
      """
      Get proactive communication insights.

      Returns:
      - Unanswered messages
      - Unreturned calls
      - Communication summary
      """
      pass

  def run_server():
      """Run the MCP server."""
      logger.info("Starting Mac Bridge MCP server...")
      mcp.run()

  if __name__ == "__main__":
      run_server()
  ```

- [ ] **Task 8.1.2**: Implement each tool function
  - [ ] `get_messages`
  - [ ] `send_message` (with confirmation)
  - [ ] `get_calls`
  - [ ] `get_call_statistics`
  - [ ] `search_contacts`
  - [ ] `list_contacts`
  - [ ] `get_insights`

- [ ] **Task 8.1.3**: Add helpful error messages for each tool

- [ ] **Test 8.1**: Test server starts
  ```bash
  cd mac-bridge-mcp
  python -m mac_bridge_mcp.server
  # Should start without errors (Ctrl+C to exit)
  ```
  **Record:** Server starts cleanly? [ ] Yes [ ] No

---

## Section 9: Integration Testing

### 9.1 End-to-End Tests

- [ ] **Task 9.1.1**: Create integration test suite
  ```python
  # tests/test_integration.py
  """Integration tests for the full MCP server."""

  def test_messages_to_contacts_resolution():
      """Test that messages correctly resolve contact names."""
      pass

  def test_calls_to_contacts_resolution():
      """Test that calls correctly resolve contact names."""
      pass

  def test_insights_finds_real_data():
      """Test that insights correctly analyzes message/call data."""
      pass
  ```

- [ ] **Test 9.1**: Run full test suite
  ```bash
  pytest tests/ -v --tb=short
  ```
  **Record:**
  - Total tests: ____
  - Passed: ____
  - Failed: ____
  - Skipped: ____

### 9.2 Manual MCP Testing

- [ ] **Task 9.2.1**: Install in Claude Code for testing
  ```bash
  # Add to project .mcp.json
  claude mcp add mac-bridge --scope project -- uv run --directory /path/to/mac-bridge/mac-bridge-mcp python -m mac_bridge_mcp.server
  ```

- [ ] **Test 9.2.1**: Test `get_messages` tool in Claude Code
  - Ask: "Get my recent messages"
  - **Record:** Messages returned with names? [ ] Yes [ ] No

- [ ] **Test 9.2.2**: Test `get_calls` tool in Claude Code
  - Ask: "Get my recent call history"
  - **Record:** Calls returned with names? [ ] Yes [ ] No

- [ ] **Test 9.2.3**: Test `search_contacts` tool in Claude Code
  - Ask: "Search contacts for Taylor"
  - **Record:** Contact found? [ ] Yes [ ] No

- [ ] **Test 9.2.4**: Test `send_message` confirmation in Claude Code
  - Ask: "Send a test message to [known contact]"
  - **Record:**
    - Confirmation dialog appeared? [ ] Yes [ ] No
    - Clicking "Cancel" prevented send? [ ] Yes [ ] No
    - Clicking "Send" sent message? [ ] Yes [ ] No

- [ ] **Test 9.2.5**: Test `get_insights` tool in Claude Code
  - Ask: "What messages haven't I responded to?"
  - **Record:** Insights returned? [ ] Yes [ ] No

---

## Section 10: Documentation and Publishing

### 10.1 Documentation

- [ ] **Task 10.1.1**: Write README.md
  - Installation instructions
  - Available tools and their parameters
  - Examples of use
  - Permissions requirements
  - Troubleshooting guide

- [ ] **Task 10.1.2**: Add inline documentation to all functions

### 10.2 Publishing

- [ ] **Task 10.2.1**: Build package
  ```bash
  cd mac-bridge-mcp
  uv build
  ```

- [ ] **Task 10.2.2**: Test installation from built package
  ```bash
  uvx --from ./dist/mac_bridge_mcp-0.1.0-py3-none-any.whl mac-bridge-mcp
  ```

- [ ] **Task 10.2.3**: Publish to PyPI (optional)
  ```bash
  uv publish
  ```

### 10.3 Final Commit

- [ ] **Task 10.3.1**: Commit all changes
  ```bash
  git add .
  git commit -m "feat: Initial mac-bridge-mcp implementation

  - Messages access with contact resolution
  - Call history with contact resolution
  - Unified contact search
  - Human-in-the-loop confirmation for sends
  - Proactive insights (unanswered messages, unreturned calls)

  🤖 Generated with Claude Code"
  git push origin main
  ```

---

## Completion Checklist

Before marking Phase 1 complete, verify:

- [ ] All unit tests pass (`pytest tests/ -v`)
- [ ] Server starts without errors
- [ ] `get_messages` returns messages with contact names
- [ ] `get_calls` returns calls with contact names
- [ ] `search_contacts` finds contacts by fuzzy name
- [ ] `send_message` shows confirmation dialog
- [ ] `send_message` only sends after user clicks "Send"
- [ ] `get_insights` returns meaningful data
- [ ] README.md is complete
- [ ] Code is committed and pushed

---

## Recording Section

**Date Started:** _________________
**Date Completed:** _________________

**Issues Encountered:**
1. _________________
2. _________________
3. _________________

**Deviations from Plan:**
1. _________________
2. _________________

**Notes for Next Phase:**
1. _________________
2. _________________

---

*This checklist is part of the Mac Bridge project. See `2025-12-18-mac-bridge-project-master-plan.md` for the full plan.*

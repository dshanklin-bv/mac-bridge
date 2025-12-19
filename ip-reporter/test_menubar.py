#!/usr/bin/env python3
"""
Tests for Mac Bridge Menu Bar App

Note: Most menu bar tests require mocking rumps which needs the GUI.
These tests focus on config and logic that can be tested without GUI.
"""

import pytest


class TestServerConfig:
    """Tests for server configuration."""

    def test_servers_configured(self):
        """Test SERVERS dict has expected entries."""
        from menubar import SERVERS

        assert "rhea-dev" in SERVERS
        assert "jetta-dev" in SERVERS
        assert SERVERS["rhea-dev"]["ip"] == "162.220.24.23"
        assert SERVERS["rhea-dev"]["tunnel_port"] == 2222

    def test_docs_url(self):
        """Test docs URL is set."""
        from menubar import DOCS_URL

        assert "github.com" in DOCS_URL
        assert "mac-bridge" in DOCS_URL

    def test_repo_path(self):
        """Test REPO_PATH points to valid directory."""
        from menubar import REPO_PATH

        assert REPO_PATH.exists()
        assert (REPO_PATH / "README.md").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
Tests for daemonctl Service Manager
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from daemonctl import ServiceManager


class TestServiceManager:
    """Tests for ServiceManager class."""

    @pytest.fixture
    def temp_config(self):
        """Create a temporary services config."""
        config_content = """
services:
  test-service:
    label: com.test.service
    description: Test service
    program: python3
    args:
      - test.py
    working_directory: /tmp/test
    run_at_load: true
    keep_alive: true
    log_path: /tmp/test.log

  another-service:
    label: com.test.another
    description: Another test service
    program: /bin/bash
    args:
      - -c
      - "echo hello"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_content)
            yield Path(f.name)

    @pytest.fixture
    def manager(self, temp_config):
        """Create a manager with test config."""
        return ServiceManager(config_path=temp_config)

    def test_init_loads_config(self, manager):
        """Test that config is loaded correctly."""
        services = manager.get_services()
        assert "test-service" in services
        assert "another-service" in services

    def test_get_service_status_unknown(self, manager):
        """Test status for unknown service."""
        status = manager.get_service_status("nonexistent")
        assert status["exists"] is False

    def test_get_service_status_known(self, manager):
        """Test status for known service."""
        status = manager.get_service_status("test-service")
        assert status["exists"] is True
        assert status["name"] == "test-service"
        assert status["label"] == "com.test.service"

    @patch('daemonctl.subprocess.run')
    def test_start_unknown_service(self, mock_run, manager, capsys):
        """Test starting unknown service."""
        result = manager.start("nonexistent")
        assert result is False
        captured = capsys.readouterr()
        assert "Unknown service" in captured.out

    @patch('daemonctl.subprocess.run')
    def test_stop_unknown_service(self, mock_run, manager, capsys):
        """Test stopping unknown service."""
        result = manager.stop("nonexistent")
        assert result is False
        captured = capsys.readouterr()
        assert "Unknown service" in captured.out


class TestPlistGenerator:
    """Tests for launchd plist generation."""

    def test_generate_basic_plist(self):
        """Test basic plist generation."""
        from generators.launchd import generate_plist

        config = {
            "label": "com.test.basic",
            "program": "python3",
            "args": ["script.py"],
            "run_at_load": True,
            "keep_alive": True,
        }

        plist = generate_plist("basic", config)

        assert "com.test.basic" in plist
        assert "python3" in plist
        assert "script.py" in plist
        assert "<true/>" in plist

    def test_generate_plist_with_logs(self):
        """Test plist with log paths."""
        from generators.launchd import generate_plist

        config = {
            "label": "com.test.withlog",
            "program": "python3",
            "args": ["script.py"],
            "log_path": "/tmp/test.log",
            "error_log_path": "/tmp/test.error.log",
        }

        plist = generate_plist("withlog", config)

        assert "StandardOutPath" in plist
        assert "/tmp/test.log" in plist
        assert "StandardErrorPath" in plist
        assert "/tmp/test.error.log" in plist


class TestSystemdGenerator:
    """Tests for systemd unit generation."""

    def test_generate_basic_unit(self):
        """Test basic systemd unit generation."""
        from generators.launchd import generate_systemd_unit

        config = {
            "description": "Test Service",
            "program": "python3",
            "args": ["script.py"],
            "working_directory": "/opt/test",
            "keep_alive": True,
        }

        unit = generate_systemd_unit("test", config)

        assert "Test Service" in unit
        assert "python3 script.py" in unit
        assert "/opt/test" in unit
        assert "Restart=always" in unit

    def test_generate_unit_no_restart(self):
        """Test unit without restart."""
        from generators.launchd import generate_systemd_unit

        config = {
            "description": "No Restart Service",
            "program": "/bin/echo",
            "args": ["hello"],
            "keep_alive": False,
        }

        unit = generate_systemd_unit("test", config)

        assert "Restart=no" in unit


class TestConfigHandling:
    """Tests for configuration edge cases."""

    def test_missing_config(self):
        """Test handling missing config file."""
        manager = ServiceManager(config_path=Path("/nonexistent/services.yaml"))
        services = manager.get_services()
        assert services == {}

    def test_empty_services(self):
        """Test empty services config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("services: {}")
            config_path = Path(f.name)

        manager = ServiceManager(config_path=config_path)
        services = manager.get_services()
        assert services == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

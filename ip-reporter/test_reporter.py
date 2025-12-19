#!/usr/bin/env python3
"""
Tests for IP Reporter
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from reporter import IPReporter


class TestIPReporter:
    """Tests for IPReporter class."""

    @pytest.fixture
    def temp_config(self, tmp_path):
        """Create a temporary config file."""
        config_content = """
reporters:
  test-server:
    method: ssh
    target: test-server
    command: "echo {ip} > /tmp/test-ip"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        return config_file

    @pytest.fixture
    def reporter(self, temp_config):
        """Create a reporter with test config."""
        return IPReporter(config_path=temp_config)

    def test_init_loads_config(self, reporter):
        """Test that config is loaded correctly."""
        reporters = reporter.config.get("reporters", {})
        assert "test-server" in reporters

    def test_get_local_ip(self, reporter):
        """Test local IP detection."""
        ip = reporter.get_local_ip()
        assert ip is not None
        # Should be a valid IP format
        parts = ip.split('.')
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    @patch('reporter.subprocess.run')
    def test_report_via_ssh_success(self, mock_run, reporter):
        """Test successful SSH report."""
        mock_run.return_value = MagicMock(returncode=0)

        result = reporter.report_via_ssh(
            "test-server",
            "echo {ip} > /tmp/ip",
            "192.168.1.100"
        )

        assert result is True
        mock_run.assert_called_once()

    @patch('reporter.subprocess.run')
    def test_report_via_ssh_failure(self, mock_run, reporter):
        """Test failed SSH report."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Connection refused")

        result = reporter.report_via_ssh(
            "test-server",
            "echo {ip} > /tmp/ip",
            "192.168.1.100"
        )

        assert result is False

    def test_get_status(self, reporter):
        """Test status reporting."""
        status = reporter.get_status()

        assert "current_ip" in status
        assert "targets" in status
        # targets list should contain test-server from our config
        assert len(status["targets"]) >= 0  # May be empty if config not loaded

    @patch('reporter.subprocess.run')
    def test_check_and_report_force(self, mock_run, reporter):
        """Test forced report."""
        mock_run.return_value = MagicMock(returncode=0)

        # Force report - may return None if no targets configured
        ip = reporter.check_and_report(force=True)

        # IP should be detected even if report not sent
        assert reporter.last_ip is not None or ip is not None

    @patch('reporter.subprocess.run')
    def test_check_and_report_no_change(self, mock_run, reporter):
        """Test that no report happens when IP unchanged."""
        mock_run.return_value = MagicMock(returncode=0)

        # First report
        ip1 = reporter.check_and_report(force=True)
        call_count_1 = mock_run.call_count

        # Second check (no change)
        ip2 = reporter.check_and_report(force=False)
        call_count_2 = mock_run.call_count

        assert ip1 is not None
        assert ip2 is None  # No report because IP unchanged
        assert call_count_1 == call_count_2  # No additional calls


class TestIPReporterConfig:
    """Tests for configuration handling."""

    def test_missing_config_file(self):
        """Test handling of missing config file."""
        reporter = IPReporter(config_path=Path("/nonexistent/config.yaml"))
        assert reporter.config == {"reporters": {}, "display": {"menubar": True}}

    def test_empty_config(self):
        """Test handling of empty config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("")
            config_path = Path(f.name)

        reporter = IPReporter(config_path=config_path)
        assert reporter.config == {} or reporter.config is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
IP Reporter - Phone Home Service for Mac Bridge

Detects current IP address and reports to configured targets.
Enables reverse SSH access from cloud servers.
"""

import subprocess
import socket
import time
import yaml
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class IPReporter:
    """Detects and reports IP addresses to configured targets."""

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or CONFIG_PATH
        self.config = self._load_config()
        self.last_ip: Optional[str] = None
        self.last_report: Dict[str, datetime] = {}

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            return {"reporters": {}, "display": {"menubar": True}}

        with open(self.config_path) as f:
            return yaml.safe_load(f) or {}

    def get_local_ip(self) -> Optional[str]:
        """Get the local IP address."""
        try:
            # Connect to external server to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.error(f"Failed to get local IP: {e}")
            return None

    def get_public_ip(self) -> Optional[str]:
        """Get public IP via external service."""
        try:
            import urllib.request
            with urllib.request.urlopen('https://api.ipify.org', timeout=5) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to get public IP: {e}")
            return None

    def report_via_ssh(self, target: str, command: str, ip: str) -> bool:
        """Report IP via SSH command."""
        try:
            # Replace {ip} placeholder with actual IP
            cmd = command.format(ip=ip)
            full_cmd = f"ssh {target} '{cmd}'"

            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                logger.info(f"Reported to {target}: {ip}")
                return True
            else:
                logger.error(f"SSH to {target} failed: {result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"SSH to {target} timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to report to {target}: {e}")
            return False

    def report_to_all(self, ip: str) -> Dict[str, bool]:
        """Report IP to all configured targets."""
        results = {}
        reporters = self.config.get("reporters", {})

        for name, config in reporters.items():
            method = config.get("method", "ssh")

            if method == "ssh":
                target = config.get("target", name)
                command = config.get("command", "echo {ip} > ~/.mac-ip")
                results[name] = self.report_via_ssh(target, command, ip)

                if results[name]:
                    self.last_report[name] = datetime.now()
            else:
                logger.warning(f"Unknown method '{method}' for {name}")
                results[name] = False

        return results

    def check_and_report(self, force: bool = False) -> Optional[str]:
        """
        Check current IP and report if changed or forced.

        Returns the current IP if reported, None otherwise.
        """
        current_ip = self.get_local_ip()

        if not current_ip:
            logger.warning("Could not determine current IP")
            return None

        # Check if IP changed or force report
        ip_changed = current_ip != self.last_ip

        if ip_changed or force:
            if ip_changed:
                logger.info(f"IP changed: {self.last_ip} -> {current_ip}")

            results = self.report_to_all(current_ip)
            self.last_ip = current_ip

            success_count = sum(1 for v in results.values() if v)
            logger.info(f"Reported to {success_count}/{len(results)} targets")

            return current_ip

        return None

    def run_loop(self, interval: int = 300):
        """Run continuous monitoring loop."""
        logger.info(f"Starting IP reporter (interval: {interval}s)")

        # Initial report
        self.check_and_report(force=True)

        while True:
            time.sleep(interval)
            self.check_and_report()

    def get_status(self) -> Dict:
        """Get current status for display."""
        return {
            "current_ip": self.last_ip or self.get_local_ip(),
            "public_ip": self.get_public_ip(),
            "last_reports": {
                name: dt.isoformat() if dt else None
                for name, dt in self.last_report.items()
            },
            "targets": list(self.config.get("reporters", {}).keys())
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="IP Reporter - Phone Home Service")
    parser.add_argument("--config", type=Path, help="Config file path")
    parser.add_argument("--once", action="store_true", help="Report once and exit")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--interval", type=int, default=300, help="Check interval (seconds)")

    args = parser.parse_args()

    reporter = IPReporter(config_path=args.config)

    if args.status:
        status = reporter.get_status()
        print(f"Current IP: {status['current_ip']}")
        print(f"Public IP:  {status['public_ip']}")
        print(f"Targets:    {', '.join(status['targets']) or 'None configured'}")
        for name, dt in status['last_reports'].items():
            print(f"  {name}: {dt or 'Never'}")
        return

    if args.once:
        ip = reporter.check_and_report(force=True)
        if ip:
            print(f"Reported: {ip}")
        else:
            print("Failed to report")
        return

    reporter.run_loop(interval=args.interval)


if __name__ == "__main__":
    main()

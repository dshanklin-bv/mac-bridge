#!/usr/bin/env python3
"""
daemonctl - Unified Service Management for Mac Bridge

Manages LaunchAgents/LaunchDaemons on macOS and systemd services on Linux.
Single source of truth for all mac-bridge services.
"""

import argparse
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Paths
SCRIPT_DIR = Path(__file__).parent
SERVICES_CONFIG = SCRIPT_DIR / "services.yaml"
LAUNCHAGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
GENERATED_DIR = SCRIPT_DIR.parent / "launchagents"


class ServiceManager:
    """Manages mac-bridge services across platforms."""

    def __init__(self, config_path: Path = None):
        self.config_path = config_path or SERVICES_CONFIG
        self.config = self._load_config()
        self.is_macos = sys.platform == "darwin"

    def _load_config(self) -> dict:
        """Load services configuration."""
        if not self.config_path.exists():
            return {"services": {}}

        with open(self.config_path) as f:
            return yaml.safe_load(f) or {}

    def _run(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and return result."""
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=check)
        except subprocess.CalledProcessError as e:
            return e

    def get_services(self) -> Dict[str, dict]:
        """Get all configured services."""
        return self.config.get("services", {})

    def get_service_status(self, name: str) -> Dict:
        """Get status of a specific service."""
        services = self.get_services()
        if name not in services:
            return {"name": name, "exists": False}

        svc = services[name]
        label = svc.get("label", f"com.mac-bridge.{name}")

        status = {
            "name": name,
            "label": label,
            "exists": True,
            "running": False,
            "pid": None,
            "installed": False,
        }

        if self.is_macos:
            # Check if plist is installed
            plist_path = LAUNCHAGENTS_DIR / f"{label}.plist"
            status["installed"] = plist_path.exists()

            # Check if running via launchctl
            result = self._run(["launchctl", "list"], check=False)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if label in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            pid = parts[0]
                            if pid != "-":
                                status["running"] = True
                                status["pid"] = int(pid)
                        break

        return status

    def status(self, service_name: str = None) -> None:
        """Show status of services."""
        services = self.get_services()

        if service_name:
            if service_name not in services:
                print(f"Unknown service: {service_name}")
                return
            services = {service_name: services[service_name]}

        print("Mac Bridge Services")
        print("=" * 50)

        for name in services:
            st = self.get_service_status(name)

            if st["running"]:
                status_icon = "✅"
                status_text = f"Running (PID {st['pid']})"
            elif st["installed"]:
                status_icon = "⏸️"
                status_text = "Stopped"
            else:
                status_icon = "❌"
                status_text = "Not installed"

            print(f"{status_icon} {name:20} {status_text}")

    def start(self, name: str) -> bool:
        """Start a service."""
        services = self.get_services()
        if name not in services:
            print(f"Unknown service: {name}")
            return False

        svc = services[name]
        label = svc.get("label", f"com.mac-bridge.{name}")
        plist_path = LAUNCHAGENTS_DIR / f"{label}.plist"

        if not plist_path.exists():
            print(f"Service not installed. Run: daemonctl install {name}")
            return False

        if self.is_macos:
            result = self._run(["launchctl", "load", str(plist_path)], check=False)
            if result.returncode == 0:
                print(f"Started {name}")
                return True
            else:
                print(f"Failed to start {name}: {result.stderr}")
                return False

        return False

    def stop(self, name: str) -> bool:
        """Stop a service."""
        services = self.get_services()
        if name not in services:
            print(f"Unknown service: {name}")
            return False

        svc = services[name]
        label = svc.get("label", f"com.mac-bridge.{name}")
        plist_path = LAUNCHAGENTS_DIR / f"{label}.plist"

        if self.is_macos:
            result = self._run(["launchctl", "unload", str(plist_path)], check=False)
            if result.returncode == 0:
                print(f"Stopped {name}")
                return True
            else:
                print(f"Failed to stop {name}: {result.stderr}")
                return False

        return False

    def restart(self, name: str) -> bool:
        """Restart a service."""
        self.stop(name)
        return self.start(name)

    def install(self, name: str = None) -> bool:
        """Install service(s) as LaunchAgent."""
        from generators.launchd import generate_plist

        services = self.get_services()
        to_install = [name] if name else list(services.keys())

        # Ensure directories exist
        GENERATED_DIR.mkdir(exist_ok=True)
        LAUNCHAGENTS_DIR.mkdir(exist_ok=True)

        for svc_name in to_install:
            if svc_name not in services:
                print(f"Unknown service: {svc_name}")
                continue

            svc = services[svc_name]
            label = svc.get("label", f"com.mac-bridge.{svc_name}")

            # Generate plist
            plist_content = generate_plist(svc_name, svc)

            # Write to generated dir
            gen_path = GENERATED_DIR / f"{label}.plist"
            with open(gen_path, "w") as f:
                f.write(plist_content)
            print(f"Generated: {gen_path}")

            # Symlink to LaunchAgents
            target_path = LAUNCHAGENTS_DIR / f"{label}.plist"
            if target_path.exists():
                target_path.unlink()
            target_path.symlink_to(gen_path)
            print(f"Installed: {target_path}")

        return True

    def uninstall(self, name: str) -> bool:
        """Uninstall a service."""
        services = self.get_services()
        if name not in services:
            print(f"Unknown service: {name}")
            return False

        svc = services[name]
        label = svc.get("label", f"com.mac-bridge.{name}")

        # Stop first
        self.stop(name)

        # Remove symlink
        target_path = LAUNCHAGENTS_DIR / f"{label}.plist"
        if target_path.exists():
            target_path.unlink()
            print(f"Uninstalled: {name}")
            return True

        print(f"Service not installed: {name}")
        return False

    def logs(self, name: str, lines: int = 50) -> None:
        """Show service logs."""
        services = self.get_services()
        if name not in services:
            print(f"Unknown service: {name}")
            return

        svc = services[name]
        log_path = svc.get("log_path")

        if log_path:
            log_file = Path(log_path).expanduser()
            if log_file.exists():
                result = self._run(["tail", f"-{lines}", str(log_file)], check=False)
                print(result.stdout)
            else:
                print(f"Log file not found: {log_file}")
        else:
            # Try system log
            label = svc.get("label", f"com.mac-bridge.{name}")
            result = self._run([
                "log", "show",
                "--predicate", f"subsystem == '{label}'",
                "--last", "1h",
                "--style", "compact"
            ], check=False)
            print(result.stdout or "No logs found")


def main():
    parser = argparse.ArgumentParser(
        description="Mac Bridge Service Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  daemonctl status              Show all services
  daemonctl status ip-reporter  Show specific service
  daemonctl start ip-reporter   Start a service
  daemonctl stop ip-reporter    Stop a service
  daemonctl install             Install all services
  daemonctl install ip-reporter Install specific service
  daemonctl logs ip-reporter    View service logs
        """
    )

    parser.add_argument("--config", type=Path, help="Services config file")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # status
    status_p = subparsers.add_parser("status", help="Show service status")
    status_p.add_argument("service", nargs="?", help="Service name (optional)")

    # start
    start_p = subparsers.add_parser("start", help="Start a service")
    start_p.add_argument("service", help="Service name")

    # stop
    stop_p = subparsers.add_parser("stop", help="Stop a service")
    stop_p.add_argument("service", help="Service name")

    # restart
    restart_p = subparsers.add_parser("restart", help="Restart a service")
    restart_p.add_argument("service", help="Service name")

    # install
    install_p = subparsers.add_parser("install", help="Install service(s)")
    install_p.add_argument("service", nargs="?", help="Service name (or all)")

    # uninstall
    uninstall_p = subparsers.add_parser("uninstall", help="Uninstall a service")
    uninstall_p.add_argument("service", help="Service name")

    # logs
    logs_p = subparsers.add_parser("logs", help="View service logs")
    logs_p.add_argument("service", help="Service name")
    logs_p.add_argument("-n", "--lines", type=int, default=50, help="Number of lines")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    mgr = ServiceManager(config_path=args.config)

    if args.command == "status":
        mgr.status(args.service)
    elif args.command == "start":
        mgr.start(args.service)
    elif args.command == "stop":
        mgr.stop(args.service)
    elif args.command == "restart":
        mgr.restart(args.service)
    elif args.command == "install":
        mgr.install(args.service)
    elif args.command == "uninstall":
        mgr.uninstall(args.service)
    elif args.command == "logs":
        mgr.logs(args.service, args.lines)


if __name__ == "__main__":
    main()

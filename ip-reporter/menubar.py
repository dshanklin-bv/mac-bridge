#!/usr/bin/env python3
"""
Mac Bridge Menu Bar App

Shows system status in the macOS menu bar:
- Current IP address
- Reverse tunnel status
- Server connectivity (rhea-dev, jetta-dev)
- Quick help and docs

Status checks are LAZY - only run when menu is opened.
"""

import subprocess
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    import rumps
except ImportError:
    print("rumps not installed. Run: pip install rumps")
    exit(1)

from reporter import IPReporter


# Server configuration
SERVERS = {
    "rhea-dev": {
        "host": "rhea-dev",
        "ip": "162.220.24.23",
        "tunnel_port": 2222,
    },
    "jetta-dev": {
        "host": "jetta-dev",
        "ip": None,
    },
}

DOCS_URL = "https://github.com/dshanklin-bv/mac-bridge"
REPO_PATH = Path(__file__).parent.parent


class MacBridgeApp(rumps.App):
    """Menu bar app for Mac Bridge status."""

    def __init__(self):
        super().__init__("∴", quit_button=None)  # Triangle of dots

        self.reporter = IPReporter()
        self._checking = False

        # Status tracking
        self.tunnel_status = {"connected": None, "last_check": None}
        self.server_status = {name: {"online": None, "last_check": None} for name in SERVERS}

        # Build menu
        self._build_menu()

    def _build_menu(self):
        """Build the menu structure."""
        # IP Section
        self.ip_item = rumps.MenuItem("📍 IP: (click to check)")
        self.public_ip_item = rumps.MenuItem("    Public: ...")

        # Tunnel Section
        self.tunnel_header = rumps.MenuItem("🔗 Tunnel")
        self.tunnel_status_item = rumps.MenuItem("    Status: (click to check)")
        self.tunnel_restart = rumps.MenuItem("    Restart Tunnel", callback=self.on_restart_tunnel)

        # Servers Section
        self.servers_header = rumps.MenuItem("🖥️ Servers")
        self.server_items = {}
        for name in SERVERS:
            self.server_items[name] = rumps.MenuItem(f"    {name}: ...")

        # Refresh
        self.refresh_item = rumps.MenuItem("🔄 Refresh Status", callback=self.on_refresh)

        # Actions Section
        self.report_now = rumps.MenuItem("📡 Report IP Now", callback=self.on_report_now)

        # Help Section
        self.help_header = rumps.MenuItem("📚 Help")
        self.help_ssh = rumps.MenuItem("    SSH to Mac from rhea-dev", callback=self.on_show_ssh_help)
        self.help_docs = rumps.MenuItem("    Open Documentation", callback=self.on_open_docs)
        self.help_logs = rumps.MenuItem("    View Logs", callback=self.on_view_logs)

        # Build menu
        self.menu = [
            self.ip_item,
            self.public_ip_item,
            rumps.separator,
            self.tunnel_header,
            self.tunnel_status_item,
            self.tunnel_restart,
            rumps.separator,
            self.servers_header,
            *self.server_items.values(),
            rumps.separator,
            self.refresh_item,
            self.report_now,
            rumps.separator,
            self.help_header,
            self.help_ssh,
            self.help_docs,
            self.help_logs,
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.on_quit),
        ]

    @rumps.clicked("📍 IP: (click to check)")
    def on_click_ip(self, _):
        """Clicking IP triggers refresh."""
        self.on_refresh(None)

    def on_refresh(self, _):
        """Refresh all status (lazy load)."""
        if self._checking:
            return

        self._checking = True
        self.refresh_item.title = "🔄 Checking..."

        def do_check():
            try:
                self._update_ip_status()
                self._update_tunnel_status()
                self._update_server_status()
                self._update_menu_bar_icon()
            finally:
                self._checking = False
                self.refresh_item.title = "🔄 Refresh Status"

        threading.Thread(target=do_check, daemon=True).start()

    def _update_ip_status(self):
        """Update IP display."""
        status = self.reporter.get_status()
        ip = status.get("current_ip", "Unknown")
        public_ip = status.get("public_ip", "Unknown")

        self.ip_item.title = f"📍 IP: {ip}"
        self.public_ip_item.title = f"    Public: {public_ip}"

    def _update_tunnel_status(self):
        """Check if tunnel is working."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=5", "rhea-dev",
                 "nc -z localhost 2222 && echo OPEN || echo CLOSED"],
                capture_output=True, text=True, timeout=10
            )

            if "OPEN" in result.stdout:
                self.tunnel_status["connected"] = True
                self.tunnel_status_item.title = "    ✅ Connected (port 2222)"
            else:
                self.tunnel_status["connected"] = False
                self.tunnel_status_item.title = "    ❌ Disconnected"

        except Exception as e:
            self.tunnel_status["connected"] = False
            self.tunnel_status_item.title = f"    ⚠️ Error: {str(e)[:20]}"

        self.tunnel_status["last_check"] = datetime.now()

    def _update_server_status(self):
        """Check server connectivity."""
        for name, config in SERVERS.items():
            try:
                result = subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes",
                     config["host"], "echo ok"],
                    capture_output=True, text=True, timeout=5
                )

                if result.returncode == 0:
                    self.server_status[name]["online"] = True
                    self.server_items[name].title = f"    ✅ {name}"
                else:
                    self.server_status[name]["online"] = False
                    self.server_items[name].title = f"    ❌ {name}"

            except subprocess.TimeoutExpired:
                self.server_status[name]["online"] = False
                self.server_items[name].title = f"    ⏳ {name} (timeout)"
            except Exception:
                self.server_status[name]["online"] = False
                self.server_items[name].title = f"    ❌ {name}"

            self.server_status[name]["last_check"] = datetime.now()

    def _update_menu_bar_icon(self):
        """Update menu bar icon based on status."""
        tunnel_ok = self.tunnel_status.get("connected")
        rhea_ok = self.server_status.get("rhea-dev", {}).get("online")

        # ∴ = therefore symbol (triangle of 3 dots)
        if tunnel_ok is None:
            self.title = "∴"  # Not checked yet
        elif tunnel_ok and rhea_ok:
            self.title = "∴"  # All good
        elif tunnel_ok:
            self.title = "∴⚠️"  # Tunnel ok, server issue
        else:
            self.title = "∴❌"  # Tunnel down

    # Callbacks

    def on_restart_tunnel(self, _):
        """Restart the reverse tunnel."""
        rumps.notification("Mac Bridge", "Restarting tunnel...", "")

        def do_restart():
            try:
                subprocess.run(
                    ["python3", str(REPO_PATH / "daemon-mgr" / "daemonctl.py"),
                     "restart", "reverse-tunnel"],
                    capture_output=True, timeout=30
                )
                # Wait and recheck
                import time
                time.sleep(3)
                self._update_tunnel_status()
                self._update_menu_bar_icon()

                if self.tunnel_status["connected"]:
                    rumps.notification("Mac Bridge", "Tunnel restarted", "✅ Connected")
                else:
                    rumps.notification("Mac Bridge", "Tunnel restart", "⚠️ May take a moment")
            except Exception as e:
                rumps.notification("Mac Bridge", "Restart failed", str(e))

        threading.Thread(target=do_restart, daemon=True).start()

    def on_report_now(self, _):
        """Report IP immediately."""
        rumps.notification("Mac Bridge", "Reporting IP...", "")

        def do_report():
            ip = self.reporter.check_and_report(force=True)
            if ip:
                rumps.notification("Mac Bridge", "IP Reported", f"Sent {ip} to all targets")
            else:
                rumps.notification("Mac Bridge", "Report failed", "Could not determine IP")

        threading.Thread(target=do_report, daemon=True).start()

    def on_show_ssh_help(self, _):
        """Show SSH help dialog."""
        rumps.alert(
            title="SSH to Mac from rhea-dev",
            message="""From rhea-dev, run:

ssh -p 2222 dshanklinbv@localhost

This connects through the reverse tunnel.

If tunnel is down, restart it from this menu."""
        )

    def on_open_docs(self, _):
        """Open documentation."""
        readme = REPO_PATH / "README.md"
        if readme.exists():
            subprocess.run(["open", str(readme)])
        else:
            webbrowser.open(DOCS_URL)

    def on_view_logs(self, _):
        """Open log files in Finder."""
        log_dir = Path.home() / "Library" / "Logs" / "mac-bridge"
        if log_dir.exists():
            subprocess.run(["open", str(log_dir)])
        else:
            rumps.alert("No logs found", f"Log directory not found:\n{log_dir}")

    def on_quit(self, _):
        """Quit the app."""
        rumps.quit_application()


def main():
    """Run the menu bar app."""
    app = MacBridgeApp()
    app.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
IP Reporter Menu Bar App

Shows current IP and report status in the macOS menu bar.
Uses rumps for the menu bar interface.
"""

import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import rumps
except ImportError:
    print("rumps not installed. Run: pip install rumps")
    exit(1)

from reporter import IPReporter, CONFIG_PATH


class IPReporterApp(rumps.App):
    """Menu bar app for IP Reporter."""

    def __init__(self):
        super().__init__("IP", quit_button=None)

        self.reporter = IPReporter()
        self.update_interval = 60  # UI update interval
        self.report_interval = 300  # Report interval (5 min)

        # Menu items
        self.ip_item = rumps.MenuItem("IP: Loading...")
        self.public_ip_item = rumps.MenuItem("Public: Loading...")
        self.separator1 = rumps.separator

        # Target status items (dynamic)
        self.target_items = {}

        self.separator2 = rumps.separator
        self.report_now = rumps.MenuItem("Report Now", callback=self.on_report_now)
        self.separator3 = rumps.separator
        self.quit_item = rumps.MenuItem("Quit", callback=self.on_quit)

        # Build initial menu
        self._build_menu()

        # Start background threads
        self._start_background_tasks()

    def _build_menu(self):
        """Build the menu structure."""
        menu_items = [
            self.ip_item,
            self.public_ip_item,
            self.separator1,
        ]

        # Add target status items
        targets = self.reporter.config.get("reporters", {})
        for name in targets:
            item = rumps.MenuItem(f"  {name}: Never reported")
            self.target_items[name] = item
            menu_items.append(item)

        if not targets:
            menu_items.append(rumps.MenuItem("  No targets configured"))

        menu_items.extend([
            self.separator2,
            self.report_now,
            self.separator3,
            self.quit_item,
        ])

        self.menu = menu_items

    def _start_background_tasks(self):
        """Start background monitoring threads."""
        # UI update thread
        ui_thread = threading.Thread(target=self._ui_update_loop, daemon=True)
        ui_thread.start()

        # Reporter thread
        report_thread = threading.Thread(target=self._report_loop, daemon=True)
        report_thread.start()

    def _ui_update_loop(self):
        """Update UI periodically."""
        while True:
            self._update_display()
            time.sleep(self.update_interval)

    def _report_loop(self):
        """Report IP periodically."""
        # Initial report
        self.reporter.check_and_report(force=True)
        self._update_display()

        while True:
            time.sleep(self.report_interval)
            self.reporter.check_and_report()
            self._update_display()

    def _update_display(self):
        """Update menu bar display."""
        status = self.reporter.get_status()

        # Update title (shows in menu bar)
        ip = status.get("current_ip", "???")
        self.title = f"📍 {ip}"

        # Update menu items
        self.ip_item.title = f"Local: {ip}"
        self.public_ip_item.title = f"Public: {status.get('public_ip', 'Unknown')}"

        # Update target status
        for name, item in self.target_items.items():
            last_report = self.reporter.last_report.get(name)
            if last_report:
                ago = self._time_ago(last_report)
                item.title = f"  📡 {name}: ✅ {ago}"
            else:
                item.title = f"  📡 {name}: ⏳ Never"

    def _time_ago(self, dt: datetime) -> str:
        """Format time as 'X ago'."""
        delta = datetime.now() - dt
        seconds = delta.total_seconds()

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            mins = int(seconds / 60)
            return f"{mins}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"

    def on_report_now(self, _):
        """Handle 'Report Now' click."""
        rumps.notification(
            title="IP Reporter",
            subtitle="Reporting...",
            message="Sending IP to all targets"
        )

        # Report in background
        def do_report():
            ip = self.reporter.check_and_report(force=True)
            self._update_display()

            if ip:
                rumps.notification(
                    title="IP Reporter",
                    subtitle="Success",
                    message=f"Reported {ip} to all targets"
                )
            else:
                rumps.notification(
                    title="IP Reporter",
                    subtitle="Failed",
                    message="Could not report IP"
                )

        thread = threading.Thread(target=do_report, daemon=True)
        thread.start()

    def on_quit(self, _):
        """Handle quit."""
        rumps.quit_application()


def main():
    """Run the menu bar app."""
    app = IPReporterApp()
    app.run()


if __name__ == "__main__":
    main()

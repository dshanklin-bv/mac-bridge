#!/usr/bin/env python3
"""
LaunchAgent/LaunchDaemon plist generator.

Generates macOS launchd plist files from service definitions.
"""

import os
from pathlib import Path
from typing import Dict


def generate_plist(name: str, config: dict) -> str:
    """
    Generate a launchd plist file content.

    Args:
        name: Service name
        config: Service configuration dict

    Returns:
        Plist XML content as string
    """
    label = config.get("label", f"com.mac-bridge.{name}")
    program = config.get("program", "python3")
    args = config.get("args", [])
    working_dir = config.get("working_directory", "")
    run_at_load = config.get("run_at_load", True)
    keep_alive = config.get("keep_alive", True)
    log_path = config.get("log_path", "")
    error_log_path = config.get("error_log_path", "")

    # Expand environment variables
    home = os.environ.get("HOME", "")
    working_dir = working_dir.replace("${HOME}", home).replace("~", home)
    log_path = log_path.replace("~", home)
    error_log_path = error_log_path.replace("~", home)

    # Ensure log directory exists
    if log_path:
        log_dir = Path(log_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    # Build program arguments
    program_args = f"""    <key>ProgramArguments</key>
    <array>
        <string>{program}</string>"""

    for arg in args:
        # Expand relative paths
        if arg.startswith("../") and working_dir:
            arg = str(Path(working_dir) / arg)
        program_args += f"\n        <string>{arg}</string>"

    program_args += "\n    </array>"

    # Build optional elements
    optional_elements = ""

    if working_dir:
        optional_elements += f"""
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>"""

    if log_path:
        optional_elements += f"""
    <key>StandardOutPath</key>
    <string>{log_path}</string>"""

    if error_log_path:
        optional_elements += f"""
    <key>StandardErrorPath</key>
    <string>{error_log_path}</string>"""

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>

{program_args}

    <key>RunAtLoad</key>
    <{"true" if run_at_load else "false"}/>

    <key>KeepAlive</key>
    <{"true" if keep_alive else "false"}/>{optional_elements}

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
"""

    return plist


def generate_systemd_unit(name: str, config: dict) -> str:
    """
    Generate a systemd unit file for Linux.

    Args:
        name: Service name
        config: Service configuration dict

    Returns:
        Systemd unit file content
    """
    description = config.get("description", f"Mac Bridge {name}")
    program = config.get("program", "python3")
    args = config.get("args", [])
    working_dir = config.get("working_directory", "")
    keep_alive = config.get("keep_alive", True)

    # Expand home
    home = os.environ.get("HOME", "")
    working_dir = working_dir.replace("${HOME}", home).replace("~", home)

    # Build exec command
    exec_args = " ".join(args)
    exec_start = f"{program} {exec_args}"

    restart = "always" if keep_alive else "no"

    unit = f"""[Unit]
Description={description}
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
WorkingDirectory={working_dir}
Restart={restart}
RestartSec=10

[Install]
WantedBy=default.target
"""

    return unit

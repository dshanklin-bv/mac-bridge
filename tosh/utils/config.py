"""
Configuration management for tosh daemon.
Loads settings from ~/.config/tosh/config.yaml
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

CONFIG_PATH = Path.home() / ".config" / "tosh" / "config.yaml"

_config: Optional[Dict[str, Any]] = None


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    global _config

    if _config is not None:
        return _config

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_PATH}\n"
            "Create it with database, tunnel, and sync settings."
        )

    with open(CONFIG_PATH) as f:
        _config = yaml.safe_load(f)

    return _config


def get(key: str, default: Any = None) -> Any:
    """
    Get a config value by dot-notation key.

    Example:
        get('database.port')  # returns 15432
        get('sync.sources')   # returns ['messages', 'calls', 'contacts']
    """
    config = load_config()
    keys = key.split('.')
    value = config

    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return default

    return value


def get_path(key: str) -> Path:
    """Get a path config value, expanding ~ to home directory."""
    value = get(key)
    if value is None:
        raise KeyError(f"Config key not found: {key}")
    return Path(os.path.expanduser(value))


def reload():
    """Force reload of configuration."""
    global _config
    _config = None
    load_config()

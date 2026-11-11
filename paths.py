"""Data and export directories. Never stores secrets in the plugin tree."""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    env = os.environ.get("SIGNALDESK_DATA_DIR")
    if env:
        path = Path(env).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    try:
        from plugins.plugin_storage import plugin_data_dir
        return Path(plugin_data_dir("signaldesk"))
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        path = home / "plugin-data" / "signaldesk"
        path.mkdir(parents=True, exist_ok=True)
        return path


def exports_dir() -> Path:
    path = data_root() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path

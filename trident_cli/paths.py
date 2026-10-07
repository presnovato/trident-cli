"""Where trident-cli keeps its data.

Nothing is ever written inside the repository.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """Resolve the data directory (creating it on first use)."""
    env = os.environ.get("TRIDENT_HOME")
    if env:
        base = Path(env).expanduser()
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) / "trident-cli" if appdata else Path.home() / "AppData" / "Roaming" / "trident-cli"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) / "trident-cli") if xdg else (Path.home() / ".local" / "share" / "trident-cli")
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    """Path to the SQLite database file."""
    return data_dir() / "trident.db"

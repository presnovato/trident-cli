"""Machine and local data diagnostics for trident-cli."""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from typing import Any

from trident_cli import __version__, output, paths, settings, storage


def _writable(path) -> bool:
    try:
        fd, name = tempfile.mkstemp(dir=str(path), prefix=".write-test-")
        os.close(fd)
        os.unlink(name)
        return True
    except OSError:
        return False


def collect() -> tuple[dict[str, Any], int]:
    data: dict[str, Any] = {
        "trident-cli": __version__,
        "python": platform.python_version(),
        "python executable": sys.executable,
        "platform": platform.platform(),
    }

    state = output.stream_state()
    data["stdout encoding (before)"] = str(state.get("stdout_before"))
    data["stdout encoding (after)"] = str(sys.stdout.encoding)
    data["probe"] = "Кириллица и 🟡"

    directory = paths.data_dir()
    data["data directory"] = str(directory)
    data["data directory writable"] = "yes" if _writable(directory) else "no"

    conn = storage.connect()
    try:
        data["database"] = str(paths.db_path())
        data["schema version"] = storage.current_version(conn)
        data["pending migrations"] = storage.pending(conn)
        timezone_value, timezone_source = settings.resolve(conn, "timezone")
        day_open_hour, _ = settings.resolve(conn, "day_open_hour")
    finally:
        conn.close()

    data["tzdata"] = "present" if settings.tzdata_available() else "missing"
    data["timezone"] = timezone_value
    data["timezone source"] = timezone_source
    if timezone_source == "default":
        data["timezone note"] = (
            "guessed from this machine; set it explicitly with "
            "trident config set timezone <IANA name or +HH:MM>"
        )
    data["day open hour"] = day_open_hour
    return data, 0


def run(_args) -> int:
    data, exit_code = collect()

    def render(report: dict) -> str:
        return chr(10).join(f"{key}: {value}" for key, value in report.items())

    output.emit(data, render)
    return exit_code

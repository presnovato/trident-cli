"""SQLite storage: connection handling and migrations."""

from __future__ import annotations

import sqlite3
from datetime import datetime, tzinfo
from pathlib import Path

from trident_cli import paths
from trident_cli.errors import CliError
from trident_cli.storage.migrations import LATEST, MIGRATIONS


def current_version(conn: sqlite3.Connection) -> int:
    """Schema version currently recorded in the database."""
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def pending(conn: sqlite3.Connection) -> int:
    """How many migrations are still to be applied."""
    version = current_version(conn)
    return sum(1 for number, _desc, _sql in MIGRATIONS if number > version)


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending migration, each in its own transaction."""
    version = current_version(conn)
    if version > LATEST:
        raise CliError(
            f"database was created by a newer trident-cli (schema {version}); upgrade the CLI"
        )
    for number, _description, sql in MIGRATIONS:
        if number <= version:
            continue
        script = f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;"
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise CliError(f"migration {number} failed: {exc}") from exc
    return current_version(conn)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database, turn on pragmas and apply pending migrations."""
    path = Path(db_path) if db_path is not None else paths.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    apply_migrations(conn)
    return conn


def open_journal(now: datetime) -> tuple[sqlite3.Connection, tzinfo, int]:
    """Connect, resolve the journal settings and close every due day.

    This is the one entry point for the commands that speak about the journal:
    ``log``, ``day``, ``stop``, ``season``, ``history`` and ``export``. Running
    it makes finished Trident days close on their own. ``doctor`` and ``config``
    use :func:`connect` instead, so merely checking the machine has no effect.
    """
    from trident_cli import closing, settings

    conn = connect()
    try:
        tz = settings.user_tzinfo(conn)
        open_hour, _source = settings.resolve(conn, "day_open_hour")
        closing.close_due_days(conn, now, tz, open_hour)
    except Exception:
        conn.close()
        raise
    return conn, tz, open_hour

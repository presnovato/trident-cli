"""Data access for the local journal.

Commands never write SQL: they call the functions here. The ``trident_day`` is
computed once, when an entry is written, from ``occurred_at`` and the settings
at that moment, so changing ``timezone`` or ``day_open_hour`` later never moves
existing entries.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timezone, tzinfo

from trident_cli import days
from trident_cli.errors import CliError

REASON_LABELS: dict[str, str] = {
    "unwell": "not feeling well",
    "no-energy": "no energy or wish to write",
    "just-because": "just because",
}
STOP_REASONS: list[str] = list(REASON_LABELS)


def _iso_utc(moment: datetime) -> str:
    """Second-precision ISO 8601 UTC with offset, e.g. ``…T09:15:00+00:00``."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _entry_json(row: sqlite3.Row) -> dict:
    return {
        "uid": row["uid"],
        "kind": row["kind"],
        "text": row["text"],
        "output": {"str": row["str_points"], "agi": row["agi_points"], "int": row["int_points"]},
        "cost": row["will_points"],
        "stop_reason": row["stop_reason"],
        "occurred_at": row["occurred_at"],
        "trident_day": row["trident_day"],
    }


def insert_entry(
    conn: sqlite3.Connection,
    *,
    kind: str,
    text: str,
    occurred_at: datetime,
    tz: tzinfo,
    open_hour: int,
    str_points: int = 0,
    agi_points: int = 0,
    int_points: int = 0,
    will_points: int = 0,
    stop_reason: str | None = None,
) -> dict:
    """Insert one entry and return it in the JSON shape, without committing.

    Callers that need the entry to be atomic with another local change wrap this
    function in their own transaction.
    """
    day = days.trident_day(occurred_at, tz, open_hour)
    last = last_closed_day(conn)
    first = _season_one_start(conn)
    if (last is not None and day <= last) or (first is not None and day < first):
        raise CliError(
            "this Trident day is already closed — check timezone and day_open_hour",
            code=1,
        )
    uid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO entries "
        "(uid, kind, text, str_points, agi_points, int_points, will_points, "
        " stop_reason, occurred_at, trident_day) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uid,
            kind,
            text,
            str_points,
            agi_points,
            int_points,
            will_points,
            stop_reason,
            _iso_utc(occurred_at),
            day.isoformat(),
        ),
    )
    row = conn.execute("SELECT * FROM entries WHERE uid = ?", (uid,)).fetchone()
    return _entry_json(row)


def add_entry(conn: sqlite3.Connection, **kwargs) -> dict:
    """Insert one entry in its own transaction and return it."""
    with conn:
        return insert_entry(conn, **kwargs)


def entry_by_uid(conn: sqlite3.Connection, uid: str) -> dict | None:
    """The entry with this uid, or ``None``."""
    row = conn.execute("SELECT * FROM entries WHERE uid = ?", (uid,)).fetchone()
    return _entry_json(row) if row is not None else None


def add_stop(
    conn: sqlite3.Connection,
    *,
    occurred_at: datetime,
    tz: tzinfo,
    open_hour: int,
    reason: str | None = None,
) -> dict | None:
    """Mark the Trident day as rest.

    Returns ``None`` when the day already has a stop entry (a second stop
    writes nothing).
    """
    day = days.trident_day(occurred_at, tz, open_hour)
    existing = conn.execute(
        "SELECT 1 FROM entries WHERE trident_day = ? AND kind = 'stop' LIMIT 1",
        (day.isoformat(),),
    ).fetchone()
    if existing is not None:
        return None
    return add_entry(
        conn,
        kind="stop",
        text="rest day",
        occurred_at=occurred_at,
        tz=tz,
        open_hour=open_hour,
        stop_reason=reason,
    )


def entries_for_day(conn: sqlite3.Connection, day: date) -> list[dict]:
    """Every entry of a Trident day, oldest first."""
    rows = conn.execute(
        "SELECT * FROM entries WHERE trident_day = ? ORDER BY occurred_at, id",
        (day.isoformat(),),
    ).fetchall()
    return [_entry_json(row) for row in rows]


def day_status(conn: sqlite3.Connection, day: date) -> str:
    """``active`` with any done entry, ``rest`` with a stop and no done entry, else ``none``.

    A day whose only entries are refusals is ``none``: letting a task go is a
    fact of the day, not a rest and not output.
    """
    rows = conn.execute(
        "SELECT kind FROM entries WHERE trident_day = ?",
        (day.isoformat(),),
    ).fetchall()
    kinds = {row["kind"] for row in rows}
    if "done" in kinds:
        return "active"
    if "stop" in kinds:
        return "rest"
    return "none"


def day_points(conn: sqlite3.Connection, day: date) -> dict:
    """Raw sums of a day's ``kind='done'`` entries, before the 10:1 conversion."""
    row = conn.execute(
        "SELECT SUM(str_points) AS s, SUM(agi_points) AS a, "
        "       SUM(int_points) AS i, SUM(will_points) AS w "
        "FROM entries WHERE trident_day = ? AND kind = 'done'",
        (day.isoformat(),),
    ).fetchone()
    return {
        "output": {"str": row["s"] or 0, "agi": row["a"] or 0, "int": row["i"] or 0},
        "cost": row["w"] or 0,
    }


def _season_one_start(conn: sqlite3.Connection) -> date | None:
    """Season 1's first day: an entry before it would never be counted."""
    row = conn.execute("SELECT start_day FROM seasons WHERE number = 1").fetchone()
    return date.fromisoformat(row["start_day"]) if row is not None else None


def last_closed_day(conn: sqlite3.Connection) -> date | None:
    """The newest day that has already been closed, or ``None``."""
    row = conn.execute("SELECT MAX(trident_day) AS m FROM closed_days").fetchone()
    return date.fromisoformat(row["m"]) if row["m"] is not None else None


def all_entries(conn: sqlite3.Connection) -> list[dict]:
    """Every entry, oldest first — the export order."""
    rows = conn.execute("SELECT * FROM entries ORDER BY occurred_at, id").fetchall()
    return [_entry_json(row) for row in rows]

"""Closing finished Trident days and rolling seasons.

The close routine is silent and idempotent: it closes every day strictly before
the current Trident day, in order and with no gaps, and rolls a season once its
28th day is closed and the current day is past it. Every closed day is written
in its own transaction; a rollover is one transaction.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone, tzinfo

from trident_cli import counting, days, journal


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _first_start(conn: sqlite3.Connection, current: date) -> date:
    """Season 1's start: the existing one, else the earliest entry, else today."""
    row = conn.execute("SELECT start_day FROM seasons WHERE number = 1").fetchone()
    if row is not None:
        return date.fromisoformat(row["start_day"])
    earliest = conn.execute("SELECT MIN(trident_day) AS m FROM entries").fetchone()
    return date.fromisoformat(earliest["m"]) if earliest["m"] is not None else current


def _ensure_season_one(conn: sqlite3.Connection, start: date) -> None:
    if conn.execute("SELECT 1 FROM seasons WHERE number = 1").fetchone() is None:
        with conn:
            conn.execute(
                "INSERT INTO seasons (number, start_day) VALUES (1, ?)",
                (start.isoformat(),),
            )


def _open_season(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute(
        "SELECT * FROM seasons WHERE closed_at IS NULL ORDER BY number DESC LIMIT 1"
    ).fetchone()


def _season_gains(conn: sqlite3.Connection, number: int) -> tuple[int, int, int, int]:
    row = conn.execute(
        "SELECT SUM(str_gain) AS s, SUM(agi_gain) AS a, "
        "       SUM(int_gain) AS i, SUM(will_gain) AS w "
        "FROM closed_days WHERE season_number = ?",
        (number,),
    ).fetchone()
    return row["s"] or 0, row["a"] or 0, row["i"] or 0, row["w"] or 0


def _close_day(conn: sqlite3.Connection, day: date, season_number: int, now: datetime) -> None:
    points = journal.day_points(conn, day)
    out = points["output"]
    gains = (
        counting.convert(out["str"]),
        counting.convert(out["agi"]),
        counting.convert(out["int"]),
        counting.convert(points["cost"]),
    )
    with conn:
        conn.execute(
            "INSERT INTO closed_days "
            "(trident_day, season_number, str_total, agi_total, int_total, will_total, "
            " str_gain, agi_gain, int_gain, will_gain, closed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                day.isoformat(),
                season_number,
                out["str"],
                out["agi"],
                out["int"],
                points["cost"],
                *gains,
                _iso_utc(now),
            ),
        )


def _roll_over(conn: sqlite3.Connection, season: sqlite3.Row, now: datetime) -> sqlite3.Row:
    number = season["number"]
    start = date.fromisoformat(season["start_day"])
    totals = _season_gains(conn, number)
    gains = tuple(counting.convert(total) for total in totals)
    with conn:
        conn.execute(
            "UPDATE seasons SET closed_at = ?, str_gain = ?, agi_gain = ?, "
            "int_gain = ?, will_gain = ? WHERE number = ?",
            (_iso_utc(now), *gains, number),
        )
        conn.execute(
            "INSERT INTO seasons (number, start_day) VALUES (?, ?)",
            (number + 1, (start + timedelta(days=counting.DAYS_PER_SEASON)).isoformat()),
        )
    return conn.execute("SELECT * FROM seasons WHERE number = ?", (number + 1,)).fetchone()


def close_due_days(
    conn: sqlite3.Connection, now: datetime, tz: tzinfo, open_hour: int
) -> None:
    """Close every Trident day before ``now``'s, in order, rolling seasons."""
    current = days.trident_day(now, tz, open_hour)
    first_start = _first_start(conn, current)
    _ensure_season_one(conn, first_start)

    season = _open_season(conn)
    last = journal.last_closed_day(conn)
    day = first_start if last is None else last + timedelta(days=1)

    while day < current:
        end = counting.season_end(date.fromisoformat(season["start_day"]))
        if day > end:
            season = _roll_over(conn, season, now)
            continue
        _close_day(conn, day, season["number"], now)
        if day == end:
            season = _roll_over(conn, season, now)
        day += timedelta(days=1)

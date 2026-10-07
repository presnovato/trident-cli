"""The read side of the slow count: seasons, the base and the day strip.

Everything here is derived with ``SUM`` over ``closed_days`` and ``seasons``;
nothing is kept as a running counter, so closing is safe to repeat.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from trident_cli import counting


def all_seasons(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every season, oldest first."""
    return conn.execute("SELECT * FROM seasons ORDER BY number").fetchall()


def closed_seasons(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM seasons WHERE closed_at IS NOT NULL ORDER BY number"
    ).fetchall()


def current_season(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The open season (the last one), or ``None`` before the first close."""
    return conn.execute(
        "SELECT * FROM seasons WHERE closed_at IS NULL ORDER BY number DESC LIMIT 1"
    ).fetchone()


def _season_row(conn: sqlite3.Connection, number: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM seasons WHERE number = ?", (number,)).fetchone()


def season_totals(conn: sqlite3.Connection, number: int) -> dict:
    """Sum of a season's closed-day gains — what the season produced."""
    row = conn.execute(
        "SELECT SUM(str_gain) AS s, SUM(agi_gain) AS a, "
        "       SUM(int_gain) AS i, SUM(will_gain) AS w "
        "FROM closed_days WHERE season_number = ?",
        (number,),
    ).fetchone()
    return {
        "output": {"str": row["s"] or 0, "agi": row["a"] or 0, "int": row["i"] or 0},
        "cost": row["w"] or 0,
    }


def season_base_gain(conn: sqlite3.Connection, number: int) -> dict | None:
    """A closed season's contribution to the base, or ``None`` while open."""
    row = _season_row(conn, number)
    if row is None or row["closed_at"] is None:
        return None
    return {
        "output": {"str": row["str_gain"], "agi": row["agi_gain"], "int": row["int_gain"]},
        "cost": row["will_gain"],
    }


def base_totals(conn: sqlite3.Connection) -> dict:
    """The life base: the sum of the closed seasons' gains."""
    row = conn.execute(
        "SELECT SUM(str_gain) AS s, SUM(agi_gain) AS a, "
        "       SUM(int_gain) AS i, SUM(will_gain) AS w "
        "FROM seasons WHERE closed_at IS NOT NULL"
    ).fetchone()
    return {
        "output": {"str": row["s"] or 0, "agi": row["a"] or 0, "int": row["i"] or 0},
        "cost": row["w"] or 0,
    }


def season_summary(conn: sqlite3.Connection, number: int) -> dict | None:
    """Everything a single-season view needs, or ``None`` for an unknown number."""
    row = _season_row(conn, number)
    if row is None:
        return None
    totals = season_totals(conn, number)
    return {
        "number": number,
        "start_day": row["start_day"],
        "end_day": counting.season_end(date.fromisoformat(row["start_day"])).isoformat(),
        "closed": row["closed_at"] is not None,
        "output": totals["output"],
        "cost": totals["cost"],
        "base_gain": season_base_gain(conn, number),
    }


def day_strip(conn: sqlite3.Connection, number: int) -> list[str]:
    """28 cells for a season: ``●`` done, ``~`` rest-only, ``·`` else."""
    row = _season_row(conn, number)
    if row is None:
        return []
    start = date.fromisoformat(row["start_day"])
    end = counting.season_end(start)
    rows = conn.execute(
        "SELECT trident_day, kind FROM entries WHERE trident_day >= ? AND trident_day <= ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    done: set[str] = set()
    rest: set[str] = set()
    for entry in rows:
        (done if entry["kind"] == "done" else rest).add(entry["trident_day"])

    cells: list[str] = []
    day = start
    while day <= end:
        key = day.isoformat()
        cells.append("●" if key in done else "~" if key in rest else "·")
        day += timedelta(days=1)
    return cells


def closed_days(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every closed day, oldest first — used by ``export``."""
    return conn.execute("SELECT * FROM closed_days ORDER BY trident_day").fetchall()


def days_with_entries(
    conn: sqlite3.Connection, since: date | None, until: date
) -> list[date]:
    """Trident days that have any entry, newest first, within ``[since, until]``."""
    query = "SELECT DISTINCT trident_day FROM entries WHERE trident_day <= ?"
    params: list[str] = [until.isoformat()]
    if since is not None:
        query += " AND trident_day >= ?"
        params.append(since.isoformat())
    query += " ORDER BY trident_day DESC"
    return [date.fromisoformat(row["trident_day"]) for row in conn.execute(query, params)]

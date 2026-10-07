"""Closing finished days: totals, gains, gaps, rollover and idempotency.

Each entry carries at most 3 points, so a day total is built from several
entries — the same way a person writes several lines in a day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import closing, journal, seasons, storage
from trident_cli.errors import CliError

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))
OPEN_HOUR = 10


def _noon_utc(day: date) -> datetime:
    """12:00 local in ``+03:00`` — safely inside the Trident day."""
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)


def _insert_one(conn, day, *, str_=0, agi=0, int_=0, will=0, kind="done"):
    return journal.add_entry(
        conn,
        kind=kind,
        text="x",
        occurred_at=_noon_utc(day),
        tz=FIXED,
        open_hour=OPEN_HOUR,
        str_points=str_,
        agi_points=agi,
        int_points=int_,
        will_points=will,
    )


def _add_day(conn, day, *, str_=0, agi=0, int_=0, will=0):
    """Write a day's points as several 1–3 point ``done`` entries."""
    chunks = []
    params = {"str": "str_", "agi": "agi", "int": "int_", "will": "will"}
    for attribute, total in (("str", str_), ("agi", agi), ("int", int_), ("will", will)):
        while total > 0:
            size = min(3, total)
            chunks.append({params[attribute]: size})
            total -= size
    for chunk in chunks or [{}]:
        _insert_one(conn, day, **chunk)


def _close(conn, now):
    closing.close_due_days(conn, now, FIXED, OPEN_HOUR)


def _closed(conn) -> dict:
    return {
        row["trident_day"]: row
        for row in conn.execute("SELECT * FROM closed_days ORDER BY trident_day")
    }


def test_first_run_creates_season_one_on_the_earliest_entry_day():
    conn = storage.connect()
    try:
        _add_day(conn, date(2026, 9, 10), str_=2)
        _close(conn, _noon_utc(date(2026, 9, 10)))

        row = conn.execute("SELECT * FROM seasons WHERE number = 1").fetchone()
        assert row["start_day"] == "2026-09-10"
        assert conn.execute("SELECT COUNT(*) c FROM closed_days").fetchone()["c"] == 0
    finally:
        conn.close()


def test_first_run_without_entries_uses_today():
    conn = storage.connect()
    try:
        _close(conn, _noon_utc(date(2026, 10, 2)))
        row = conn.execute("SELECT start_day FROM seasons WHERE number = 1").fetchone()
        assert row["start_day"] == "2026-10-02"
    finally:
        conn.close()


def test_a_finished_day_closes_with_totals_and_gains():
    conn = storage.connect()
    try:
        _add_day(conn, date(2026, 9, 1), str_=25, agi=1, will=11)
        _close(conn, _noon_utc(date(2026, 9, 2)))

        row = _closed(conn)["2026-09-01"]
        assert (row["str_total"], row["agi_total"], row["int_total"], row["will_total"]) == (25, 1, 0, 11)
        assert (row["str_gain"], row["agi_gain"], row["int_gain"], row["will_gain"]) == (3, 1, 0, 2)
        assert conn.execute("SELECT COUNT(*) c FROM closed_days").fetchone()["c"] == 1
    finally:
        conn.close()


def test_stop_entries_do_not_count():
    conn = storage.connect()
    try:
        _insert_one(conn, date(2026, 9, 1), kind="stop")
        _close(conn, _noon_utc(date(2026, 9, 2)))

        row = _closed(conn)["2026-09-01"]
        assert (row["str_total"], row["agi_total"], row["int_total"], row["will_total"]) == (0, 0, 0, 0)
        assert row["str_gain"] == 0
    finally:
        conn.close()


def test_a_day_without_entries_closes_with_zeros():
    conn = storage.connect()
    try:
        _add_day(conn, date(2026, 9, 1), str_=1)
        _close(conn, _noon_utc(date(2026, 9, 4)))

        rows = _closed(conn)
        assert set(rows) == {"2026-09-01", "2026-09-02", "2026-09-03"}
        assert rows["2026-09-02"]["str_total"] == 0
    finally:
        conn.close()


def test_closing_twice_changes_nothing():
    conn = storage.connect()
    try:
        _add_day(conn, date(2026, 9, 1), str_=5)
        _close(conn, _noon_utc(date(2026, 9, 3)))
        first_days = conn.execute("SELECT COUNT(*) c FROM closed_days").fetchone()["c"]
        first_seasons = conn.execute("SELECT COUNT(*) c FROM seasons").fetchone()["c"]

        _close(conn, _noon_utc(date(2026, 9, 3)))

        assert conn.execute("SELECT COUNT(*) c FROM closed_days").fetchone()["c"] == first_days
        assert conn.execute("SELECT COUNT(*) c FROM seasons").fetchone()["c"] == first_seasons
    finally:
        conn.close()


def test_a_40_day_gap_closes_40_days_in_order():
    conn = storage.connect()
    try:
        _close(conn, _noon_utc(date(2026, 9, 1)))
        _close(conn, _noon_utc(date(2026, 10, 11)))

        days = list(_closed(conn))
        assert len(days) == 40
        assert days[0] == "2026-09-01"
        assert days[-1] == "2026-10-10"

        first = conn.execute("SELECT * FROM seasons WHERE number = 1").fetchone()
        second = conn.execute("SELECT * FROM seasons WHERE number = 2").fetchone()
        assert first["closed_at"] is not None
        assert second["start_day"] == "2026-09-29"
        assert second["closed_at"] is None
    finally:
        conn.close()


def test_a_60_day_gap_rolls_two_seasons():
    conn = storage.connect()
    try:
        _close(conn, _noon_utc(date(2026, 9, 1)))
        _close(conn, _noon_utc(date(2026, 10, 31)))

        third = conn.execute("SELECT * FROM seasons WHERE number = 3").fetchone()
        assert third["start_day"] == "2026-10-27"  # start + 56

        for number in (1, 2):
            row = conn.execute("SELECT * FROM seasons WHERE number = ?", (number,)).fetchone()
            assert row["closed_at"] is not None
        assert third["closed_at"] is None
    finally:
        conn.close()


def test_rollover_converts_season_totals_and_base():
    conn = storage.connect()
    try:
        _add_day(conn, date(2026, 9, 1), str_=30, will=10)
        _close(conn, _noon_utc(date(2026, 9, 1)))
        _close(conn, _noon_utc(date(2026, 9, 29)))

        first = conn.execute("SELECT * FROM seasons WHERE number = 1").fetchone()
        assert first["str_gain"] == 1  # ceil(3 / 10)
        assert first["will_gain"] == 1

        base = seasons.base_totals(conn)
        assert base["output"]["str"] == 1
        assert base["cost"] == 1
    finally:
        conn.close()


def test_a_late_entry_into_a_closed_day_is_refused():
    conn = storage.connect()
    try:
        _close(conn, _noon_utc(date(2026, 9, 1)))
        _close(conn, _noon_utc(date(2026, 9, 5)))

        with pytest.raises(CliError, match="already closed"):
            _insert_one(conn, date(2026, 9, 3), str_=1)
        assert conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"] == 0
    finally:
        conn.close()


def test_an_entry_before_season_one_is_refused():
    # Season 1 exists but no day is closed yet; an entry that lands before its
    # start (e.g. after moving day_open_hour) would never be counted.
    conn = storage.connect()
    try:
        _close(conn, _noon_utc(date(2026, 9, 5)))

        with pytest.raises(CliError, match="already closed"):
            _insert_one(conn, date(2026, 9, 4), str_=1)
        assert conn.execute("SELECT COUNT(*) c FROM entries").fetchone()["c"] == 0
    finally:
        conn.close()


def test_doctor_and_config_do_not_close_days(cli):
    assert cli("doctor")[0] == 0
    assert cli("config", "list")[0] == 0

    conn = storage.connect()
    try:
        assert conn.execute("SELECT COUNT(*) c FROM seasons").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM closed_days").fetchone()["c"] == 0
    finally:
        conn.close()

"""Plan rules and day status."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import journal, plan, storage
from trident_cli.errors import CliError

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))
OPEN_HOUR = 10


def _noon_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)


def _conn():
    return storage.connect()


def _add(conn, text, day=date(2026, 9, 1)):
    return plan.add_task(conn, text=text, now=_noon_utc(day), tz=FIXED, open_hour=OPEN_HOUR)


def _complete(conn, task_id, **points):
    return plan.complete_task(
        conn, task_id=task_id, now=_noon_utc(date(2026, 9, 1)), tz=FIXED, open_hour=OPEN_HOUR, **points
    )


def _refuse(conn, task_id):
    return plan.refuse_task(
        conn, task_id=task_id, now=_noon_utc(date(2026, 9, 1)), tz=FIXED, open_hour=OPEN_HOUR
    )


# --- migration 4 ------------------------------------------------------------




# --- day status -------------------------------------------------------------


def test_day_status_treats_a_refusal_only_day_as_none():
    conn = _conn()
    try:
        task = _add(conn, "Old newsletter draft")
        plan.refuse_task(
            conn, task_id=task["id"], now=_noon_utc(date(2026, 9, 1)), tz=FIXED, open_hour=OPEN_HOUR
        )
        assert journal.day_status(conn, date(2026, 9, 1)) == "none"

        journal.add_stop(conn, occurred_at=_noon_utc(date(2026, 9, 2)), tz=FIXED, open_hour=OPEN_HOUR)
        assert journal.day_status(conn, date(2026, 9, 2)) == "rest"

        journal.add_entry(
            conn,
            kind="done",
            text="x",
            occurred_at=_noon_utc(date(2026, 9, 3)),
            tz=FIXED,
            open_hour=OPEN_HOUR,
            str_points=1,
        )
        assert journal.day_status(conn, date(2026, 9, 3)) == "active"
    finally:
        conn.close()


# --- the six-task rule ------------------------------------------------------


def test_the_seventh_open_task_is_refused():
    conn = _conn()
    try:
        for index in range(6):
            _add(conn, f"task {index}")
        with pytest.raises(CliError, match="6 open tasks"):
            _add(conn, "one too many")
        assert plan.open_count(conn) == 6
    finally:
        conn.close()


def test_completing_refusing_and_moving_free_a_place():
    conn = _conn()
    try:
        ids = [_add(conn, f"task {index}")["id"] for index in range(6)]
        _complete(conn, ids[0], str_points=2)
        seventh = _add(conn, "after done")
        assert seventh["id"] == 7

        _refuse(conn, ids[1])
        assert _add(conn, "after refuse")["id"] == 8

        plan.move_to_aion(conn, task_id=ids[2], now=_noon_utc(date(2026, 9, 1)))
        assert _add(conn, "after move")["id"] == 9
        assert plan.open_count(conn) == 6
    finally:
        conn.close()


def test_pulling_an_idea_takes_a_place_and_respects_the_limit():
    conn = _conn()
    try:
        for index in range(6):
            _add(conn, f"task {index}")
        idea = plan.add_idea(conn, text="Learn to sail", why="calm", now=_noon_utc(date(2026, 9, 1)))

        with pytest.raises(CliError, match="6 open tasks"):
            plan.pull_idea(
                conn, idea_id=idea["id"], now=_noon_utc(date(2026, 9, 1)), tz=FIXED, open_hour=OPEN_HOUR
            )
        # The idea stays in Aion.
        assert plan.open_ideas(conn)[0]["status"] == "open"

        plan.refuse_task(
            conn,
            task_id=plan.open_tasks(conn, date(2026, 9, 1))["plan"][0]["id"],
            now=_noon_utc(date(2026, 9, 1)),
            tz=FIXED,
            open_hour=OPEN_HOUR,
        )
        task, pulled = plan.pull_idea(
            conn, idea_id=idea["id"], now=_noon_utc(date(2026, 9, 1)), tz=FIXED, open_hour=OPEN_HOUR
        )
        assert task["text"] == "Learn to sail"
        assert task["from_aion"] == idea["id"]
        assert pulled["status"] == "pulled"
        assert plan.open_ideas(conn) == []
    finally:
        conn.close()


def test_ids_are_stable():
    conn = _conn()
    try:
        first = _add(conn, "first")
        second = _add(conn, "second")
        third = _add(conn, "third")
        _complete(conn, second["id"])

        fourth = _add(conn, "fourth")
        assert [first["id"], second["id"], third["id"], fourth["id"]] == [1, 2, 3, 4]
    finally:
        conn.close()


def test_parse_id_accepts_hash_and_plain():
    assert plan.parse_id("12") == 12
    assert plan.parse_id("#12") == 12
    with pytest.raises(CliError):
        plan.parse_id("abc")
    with pytest.raises(CliError):
        plan.parse_id("0")


def test_unknown_and_closed_ids_are_errors():
    conn = _conn()
    try:
        task = _add(conn, "done soon")
        with pytest.raises(CliError, match="no open task #99"):
            _complete(conn, 99)
        _complete(conn, task["id"])
        with pytest.raises(CliError, match=f"no open task #{task['id']}"):
            _complete(conn, task["id"])
    finally:
        conn.close()


# --- completion and refusal -------------------------------------------------


def test_completion_writes_an_entry_with_the_task_text():
    conn = _conn()
    try:
        task = _add(conn, "Write the report")
        done = _complete(conn, task["id"], int_points=2, will_points=1)
        assert done["status"] == "done"
        assert done["entry"]["text"] == "Write the report"
        assert done["entry"]["kind"] == "done"
        assert done["entry"]["output"] == {"str": 0, "agi": 0, "int": 2}
        assert done["entry"]["cost"] == 1
    finally:
        conn.close()


def test_silent_completion_writes_no_entry():
    conn = _conn()
    try:
        task = _add(conn, "Already written")
        done = plan.complete_task(
            conn,
            task_id=task["id"],
            now=_noon_utc(date(2026, 9, 1)),
            tz=FIXED,
            open_hour=OPEN_HOUR,
            silent=True,
        )
        assert done["entry"] is None
        assert conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"] == 0
    finally:
        conn.close()


def test_task_and_entry_are_written_atomically(monkeypatch):
    conn = _conn()
    try:
        task = _add(conn, "Atomic")

        def boom(*_args, **_kwargs):
            raise RuntimeError("entry insert failed")

        monkeypatch.setattr(journal, "insert_entry", boom)
        with pytest.raises(RuntimeError):
            _complete(conn, task["id"])

        row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task["id"],)).fetchone()
        assert row["status"] == "pending"
        assert conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"] == 0
    finally:
        conn.close()


def test_refusal_writes_a_zero_point_entry():
    conn = _conn()
    try:
        task = _add(conn, "Old newsletter draft")
        refused = _refuse(conn, task["id"])
        assert refused["status"] == "refused"
        assert refused["entry"]["kind"] == "refuse"
        assert refused["entry"]["output"] == {"str": 0, "agi": 0, "int": 0}
        assert refused["entry"]["cost"] == 0
        points = journal.day_points(conn, date(2026, 9, 1))
        assert points == {"output": {"str": 0, "agi": 0, "int": 0}, "cost": 0}
    finally:
        conn.close()


def test_move_to_aion_creates_an_idea_with_the_same_text():
    conn = _conn()
    try:
        task = _add(conn, "Fix the bike light")
        moved, idea = plan.move_to_aion(conn, task_id=task["id"], now=_noon_utc(date(2026, 9, 1)))
        assert moved["status"] == "moved"
        assert idea["text"] == "Fix the bike light"
        assert idea["status"] == "open"
        assert [item["text"] for item in plan.open_ideas(conn)] == ["Fix the bike light"]
    finally:
        conn.close()


def test_drop_hides_an_idea():
    conn = _conn()
    try:
        idea = plan.add_idea(conn, text="Learn to sail", why=None, now=_noon_utc(date(2026, 9, 1)))
        dropped = plan.drop_idea(conn, idea_id=idea["id"], now=_noon_utc(date(2026, 9, 1)))
        assert dropped["status"] == "dropped"
        assert plan.open_ideas(conn) == []
    finally:
        conn.close()


def test_open_ideas_are_oldest_first_with_why():
    conn = _conn()
    try:
        plan.add_idea(conn, text="first", why="because", now=_noon_utc(date(2026, 9, 1)))
        plan.add_idea(conn, text="second", why=None, now=_noon_utc(date(2026, 9, 2)))
        ideas = plan.open_ideas(conn)
        assert [idea["text"] for idea in ideas] == ["first", "second"]
        assert ideas[0]["why"] == "because"
    finally:
        conn.close()

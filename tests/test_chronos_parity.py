"""Local Chronos behavior: dated tasks, planning fields and steps."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import clock, storage

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))
PENALTY_WORDS = ("overdue", "late", "missed", "failed", "refused", "%")

@pytest.fixture
def at_time(monkeypatch):
    def set_time(moment: datetime):
        monkeypatch.setattr(clock, "now", lambda: moment)

    return set_time

def _noon_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)

def _set_tz(cli) -> None:
    assert cli("config", "set", "timezone", "+03:00")[0] == 0
    assert cli("config", "set", "day_open_hour", "10")[0] == 0

def _db():
    return storage.connect()

# --- task planning ----------------------------------------------------------

# --- dates and capacity -----------------------------------------------------

def test_add_defaults_to_today_and_accepts_a_chosen_date(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))

    today = json.loads(cli("--json", "task", "add", "Today")[1])
    assert today["task_date"] == "2026-10-05"

    future = json.loads(cli("--json", "task", "add", "--date", "2026-10-15", "Later")[1])
    assert future["task_date"] == "2026-10-15"

    past = json.loads(cli("--json", "task", "add", "--date", "2026-01-02", "Past")[1])
    assert past["task_date"] == "2026-01-02"

    listing = json.loads(cli("--json", "task", "list", "--date", "2026-10-15")[1])
    assert [task["text"] for task in listing["plan"]] == ["Later"]
    assert listing["date"] == "2026-10-15"

    # Future and past tasks stay visible from today, in their own groups.
    today_list = json.loads(cli("--json", "task", "list")[1])
    assert [task["text"] for task in today_list["plan"]] == ["Today"]
    assert [task["text"] for task in today_list["from_earlier"]] == ["Past"]
    assert [task["text"] for task in today_list["later"]] == ["Later"]

def test_an_invalid_date_changes_nothing(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    code, out, err = cli("task", "add", "--date", "not-a-date", "x")
    assert code == 2
    assert out == ""
    assert "not a date" in err
    assert json.loads(cli("--json", "task", "list")[1])["plan"] == []

def test_capacity_is_per_day(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    for index in range(6):
        assert cli("task", "add", "--date", "2026-10-05", f"task {index}")[0] == 0

    code, out, err = cli("task", "add", "--date", "2026-10-05", "one too many")
    assert code == 1
    assert out == ""
    assert "6 open tasks" in err

    # A different day still has its own room.
    assert cli("task", "add", "--date", "2026-10-06", "another day")[0] == 0
    assert json.loads(cli("--json", "task", "list", "--date", "2026-10-06")[1])["plan"][0][
        "text"
    ] == "another day"

def test_move_respects_the_target_capacity(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    for index in range(6):
        cli("task", "add", "--date", "2026-10-05", f"task {index}")
    movable = json.loads(cli("--json", "task", "add", "--date", "2026-10-07", "move me")[1])

    code, _out, err = cli("task", "move", str(movable["id"]), "--date", "2026-10-05")
    assert code == 1
    assert "6 open tasks" in err

    assert cli("task", "move", str(movable["id"]), "--date", "2026-11-01")[0] == 0
    listing = json.loads(cli("--json", "task", "list", "--date", "2026-11-01")[1])
    assert [task["text"] for task in listing["plan"]] == ["move me"]

# --- fields -----------------------------------------------------------------

def test_fields_can_be_set_read_and_survive_a_restart(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    task = json.loads(
        cli(
            "--json",
            "task",
            "add",
            "--date",
            "2026-10-05",
            "--note",
            "a description",
            "--remind",
            "09:30",
            "--frog",
            "--epic",
            "3",
            "Write it",
        )[1]
    )
    assert task["note"] == "a description"
    assert task["remind_at"] == "09:30"
    assert task["is_frog"] is True
    assert task["strategy"] == {"kind": "epic", "id": 3, "title": None}

    conn = _db()
    try:
        task_id = conn.execute("SELECT id FROM tasks WHERE uid = ?", (task["uid"],)).fetchone()["id"]
    finally:
        conn.close()

    shown = json.loads(cli("--json", "task", "show", str(task_id))[1])
    assert shown["note"] == "a description"
    assert shown["is_frog"] is True
    assert shown["strategy"]["kind"] == "epic"

def test_edit_changes_and_clears_fields(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    task = json.loads(cli("--json", "task", "add", "Edit me")[1])
    ident = str(task["id"])

    assert cli("task", "edit", ident, "--note", "n", "--remind", "08:00", "--frog")[0] == 0
    assert cli("task", "edit", ident, "--no-frog", "--no-remind")[0] == 0
    assert cli("task", "edit", ident, "--no-underline")[0] == 0
    assert cli("task", "edit", ident, "--underline")[0] == 0
    after = json.loads(cli("--json", "task", "show", ident)[1])
    assert after["note"] == "n"
    assert after["remind_at"] is None
    assert after["is_frog"] is False
    assert after["below_line"] is True
    assert after["task_date"] is None

    assert cli("task", "edit", ident, "--no-underline", "--date", "2026-10-09")[0] == 0
    back = json.loads(cli("--json", "task", "show", ident)[1])
    assert back["below_line"] is False
    assert back["task_date"] == "2026-10-09"

    assert cli("task", "edit", ident, "--sprint", "5")[0] == 0
    assert json.loads(cli("--json", "task", "show", ident)[1])["strategy"] == {
        "kind": "sprint",
        "id": 5,
        "title": None,
    }
    assert cli("task", "edit", ident, "--no-strategy")[0] == 0
    assert json.loads(cli("--json", "task", "show", ident)[1])["strategy"] is None
    assert cli("task", "edit", ident)[0] == 2  # nothing to change

def test_underline_tasks_do_not_count_for_a_day(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    for index in range(6):
        cli("task", "add", "--date", "2026-10-05", f"task {index}")
    assert cli("task", "add", "--underline", "floating")[0] == 0

    listing = json.loads(cli("--json", "task", "list")[1])
    assert [task["text"] for task in listing["underline"]] == ["floating"]

# --- steps ------------------------------------------------------------------

def test_steps_track_progress_without_a_percentage(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    task = json.loads(cli("--json", "task", "add", "Steps")[1])
    ident = str(task["id"])

    assert cli("task", "step", "add", ident, "first")[0] == 0
    assert cli("task", "step", "add", ident, "second")[0] == 0
    assert cli("task", "step", "done", ident, "1")[0] == 0
    assert cli("task", "step", "skip", ident, "2")[0] == 0

    shown = json.loads(cli("--json", "task", "show", ident)[1])
    assert [(step["text"], step["is_done"], step["is_skipped"]) for step in shown["steps"]] == [
        ("first", True, False),
        ("second", False, True),
    ]

    assert cli("task", "step", "resume", ident, "2")[0] == 0
    assert json.loads(cli("--json", "task", "show", ident)[1])["steps"][1]["is_skipped"] is False

    human = cli("task", "list")[1]
    assert "1 of 2 steps" in human
    assert "%" not in human

    code, _out, err = cli("task", "step", "done", ident, "9")
    assert code == 1
    assert "no step 9" in err

def test_moving_to_aion_and_back_keeps_the_steps(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    task = json.loads(cli("--json", "task", "add", "Steps move")[1])
    ident = str(task["id"])
    cli("task", "step", "add", ident, "one")
    cli("task", "step", "add", ident, "two")

    assert cli("task", "later", ident)[0] == 0
    idea = json.loads(cli("--json", "aion", "list")[1])["ideas"][0]
    assert [step["text"] for step in idea["steps"]] == ["one", "two"]

    assert cli("aion", "pull", str(idea["id"]))[0] == 0
    pulled = json.loads(cli("--json", "task", "list")[1])["plan"][0]
    assert [step["text"] for step in pulled["steps"]] == ["one", "two"]

def test_aion_note_travels_with_the_idea(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    idea = json.loads(
        cli("--json", "aion", "add", "Learn to sail", "--why", "calm", "--note", "ask around")[1]
    )
    assert idea["note"] == "ask around"
    assert "note: ask around" in cli("aion", "list")[1]

    assert cli("aion", "pull", str(idea["id"]))[0] == 0
    task = json.loads(cli("--json", "task", "list")[1])["plan"][0]
    assert task["note"] == "ask around"

# --- wording ----------------------------------------------------------------

@pytest.mark.parametrize("word", PENALTY_WORDS)
def test_parity_output_never_judges(cli, at_time, word):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 5)))
    task = json.loads(cli("--json", "task", "add", "--note", "n", "--remind", "09:00", "T")[1])
    ident = str(task["id"])
    cli("task", "step", "add", ident, "one")
    cli("task", "step", "done", ident, "1")

    combined = "\n".join(
        [
            cli("task", "list")[1],
            cli("task", "show", ident)[1],
            cli("task", "move", ident, "--date", "2026-10-06")[1],
            cli("task", "edit", ident, "--no-frog")[1],
        ]
    ).lower()
    assert word not in combined

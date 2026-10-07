"""``trident task`` / ``done`` / ``refuse`` / ``aion`` end to end."""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import clock

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))
PENALTY_WORDS = ("overdue", "late", "missed", "failed", "refused", "%", "2/6")


class TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.fixture
def at_time(monkeypatch):
    def set_time(moment: datetime):
        monkeypatch.setattr(clock, "now", lambda: moment)

    return set_time


def _set_tz(cli) -> None:
    assert cli("config", "set", "timezone", "+03:00")[0] == 0
    assert cli("config", "set", "day_open_hour", "10")[0] == 0


def _noon_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)


def _add_task(cli, at_time, text, day=date(2026, 9, 1)):
    at_time(_noon_utc(day))
    code, out, err = cli("--json", "task", "add", text)
    assert code == 0, err
    return json.loads(out)


def _add_idea(cli, at_time, text, why=None, day=date(2026, 9, 1)):
    at_time(_noon_utc(day))
    args = ["--json", "aion", "add", text]
    if why is not None:
        args += ["--why", why]
    code, out, err = cli(*args)
    assert code == 0, err
    return json.loads(out)


def _feed_input(monkeypatch, answers):
    queue = list(answers)

    def fake_input():
        if not queue:
            raise EOFError
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


def test_task_add_then_done_writes_the_entry(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Write the report")
    assert task["id"] == 1
    assert task["from_aion"] is None

    at_time(_noon_utc(date(2026, 9, 1)))
    code, out, err = cli("done", "1", "+2", "INT")
    assert code == 0
    assert out.strip() == "Done #1 · INT +2"

    listing = json.loads(cli("--json", "task", "list")[1])
    assert listing["plan"] == []
    assert [item["id"] for item in listing["done_today"]] == [1]
    assert listing["done_today"][0]["entry"]["output"]["int"] == 2

    day = json.loads(cli("--json", "day")[1])
    assert day["entries"][0]["text"] == "Write the report"
    assert day["entries"][0]["output"]["int"] == 2


def test_task_text_is_not_parsed_for_attributes(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Read +2 INT notes")
    assert task["text"] == "Read +2 INT notes"
    assert "Read +2 INT notes" in cli("task", "list")[1]


def test_the_seventh_open_task_is_refused(cli, at_time):
    _set_tz(cli)
    for index in range(6):
        _add_task(cli, at_time, f"task {index}")

    at_time(_noon_utc(date(2026, 9, 1)))
    code, out, err = cli("task", "add", "one too many")
    assert code == 1
    assert out == ""
    assert "6 open tasks" in err
    assert len(json.loads(cli("--json", "task", "list")[1])["plan"]) == 6


def test_refusal_shows_in_day_and_not_in_the_season(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 9, 1)))
    assert cli("log", "Ran", "+3", "STR")[0] == 0

    task = _add_task(cli, at_time, "Old newsletter draft", day=date(2026, 9, 2))
    at_time(_noon_utc(date(2026, 9, 2)))
    code, out, err = cli("refuse", str(task["id"]))
    assert code == 0
    assert out.strip() == "Let go #1."

    day = json.loads(cli("--json", "day")[1])
    assert day["status"] == "none"
    assert day["entries"][0]["kind"] == "refuse"
    assert "let go · Old newsletter draft" in cli("day")[1]

    # 9/1 closes with STR 1; the refusal-only 9/2 adds nothing.
    at_time(_noon_utc(date(2026, 9, 3)))
    assert json.loads(cli("--json", "season")[1])["output"]["str"] == 1


def test_aion_add_list_pull(cli, at_time):
    _set_tz(cli)
    _add_idea(cli, at_time, "Learn to sail", why="calm")
    at_time(_noon_utc(date(2026, 9, 1)))

    out = cli("aion", "list")[1]
    assert "#1  Learn to sail" in out
    assert "why: calm" in out

    code, out, err = cli("aion", "pull", "1")
    assert code == 0
    assert out.strip() == "Pulled #1 into the plan as #1."

    listing = json.loads(cli("--json", "task", "list")[1])
    assert [item["text"] for item in listing["plan"]] == ["Learn to sail"]
    assert json.loads(cli("--json", "aion", "list")[1])["ideas"] == []


def test_task_later_moves_an_open_task_to_aion(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Fix the bike light")
    at_time(_noon_utc(date(2026, 9, 1)))

    code, out, _err = cli("task", "later", str(task["id"]))
    assert code == 0
    assert out.strip() == "Moved #1 to Aion as #1."
    ideas = json.loads(cli("--json", "aion", "list")[1])["ideas"]
    assert [idea["text"] for idea in ideas] == ["Fix the bike light"]


def test_aion_drop_hides_an_idea(cli, at_time):
    _set_tz(cli)
    _add_idea(cli, at_time, "Learn to sail")
    at_time(_noon_utc(date(2026, 9, 1)))

    code, out, _err = cli("aion", "drop", "#1")
    assert code == 0
    assert out.strip() == "Dropped #1."
    assert json.loads(cli("--json", "aion", "list")[1])["ideas"] == []


def test_plain_output_is_scriptable(cli, at_time):
    _set_tz(cli)
    _add_task(cli, at_time, "Write the report")
    _add_task(cli, at_time, "Call the bank")
    _add_idea(cli, at_time, "Learn to sail")
    at_time(_noon_utc(date(2026, 9, 1)))

    lines = cli("task", "list", "--plain")[1].splitlines()
    assert [line.split("\t")[0] for line in lines] == ["1", "2"]
    assert lines[0].split("\t")[1] == "Write the report"

    idea_lines = cli("aion", "list", "--plain")[1].splitlines()
    assert idea_lines == ["1\tLearn to sail"]


def test_a_task_from_an_earlier_day_is_carry_over(cli, at_time):
    _set_tz(cli)
    _add_task(cli, at_time, "Fix the bike light", day=date(2026, 9, 1))
    at_time(_noon_utc(date(2026, 9, 2)))

    out = cli("task", "list")[1]
    assert "From earlier" in out
    assert "Fix the bike light" in out
    assert "2026-09-01" not in out

    payload = json.loads(cli("--json", "task", "list")[1])
    assert payload["plan"] == []
    assert [task["text"] for task in payload["from_earlier"]] == ["Fix the bike light"]


def test_empty_plan_and_aion_messages(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 9, 1)))
    assert "The plan is clear." in cli("task", "list")[1]
    assert "Aion is empty." in cli("aion", "list")[1]


def test_done_silent_writes_no_entry(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Already written")
    at_time(_noon_utc(date(2026, 9, 1)))

    code, out, _err = cli("done", str(task["id"]), "--silent")
    assert code == 0
    assert out.strip() == "Done #1."
    assert json.loads(cli("--json", "day")[1])["entries"] == []


def test_done_silent_with_pairs_is_a_usage_error(cli, at_time):
    _set_tz(cli)
    _add_task(cli, at_time, "x")
    at_time(_noon_utc(date(2026, 9, 1)))

    code, _out, _err = cli("done", "1", "--silent", "+2", "INT")
    assert code == 2


def test_done_interactive(cli, at_time, monkeypatch):
    _set_tz(cli)
    _add_task(cli, at_time, "Call the bank")
    monkeypatch.setattr("sys.stdin", TTY(""))
    _feed_input(monkeypatch, ["2", "", "1", "3"])
    at_time(_noon_utc(date(2026, 9, 1)))

    code, out, _err = cli("done", "1", "-i")
    assert code == 0
    assert "STR +2" in out and "🟡 3" in out

    entry = json.loads(cli("--json", "day")[1])["entries"][0]
    assert entry["output"] == {"str": 2, "agi": 0, "int": 1}
    assert entry["cost"] == 3


def test_unknown_ids_exit_one(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 9, 1)))

    code, _out, err = cli("done", "99")
    assert code == 1
    assert "no open task #99" in err

    code, _out, err = cli("refuse", "99")
    assert code == 1
    assert "no open task #99" in err

    code, _out, err = cli("aion", "drop", "99")
    assert code == 1
    assert "no idea #99 in Aion" in err


def test_history_lists_a_refusal_only_day(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Old newsletter draft")
    at_time(_noon_utc(date(2026, 9, 1)))
    assert cli("refuse", str(task["id"]))[0] == 0

    at_time(_noon_utc(date(2026, 9, 2)))
    payload = json.loads(cli("--json", "history")[1])
    assert [day["trident_day"] for day in payload["days"]] == ["2026-09-01"]
    assert "let go · Old newsletter draft" in cli("history")[1]


def test_export_includes_tasks_and_aion(cli, at_time):
    _set_tz(cli)
    _add_task(cli, at_time, "Write the report")
    _add_idea(cli, at_time, "Learn to sail", why="calm")
    at_time(_noon_utc(date(2026, 9, 1)))

    payload = json.loads(cli("export")[1])
    assert [task["text"] for task in payload["tasks"]] == ["Write the report"]
    assert [idea["text"] for idea in payload["aion"]] == ["Learn to sail"]


def test_export_csv_keeps_refusal_rows(cli, at_time):
    _set_tz(cli)
    task = _add_task(cli, at_time, "Old newsletter draft")
    at_time(_noon_utc(date(2026, 9, 1)))
    assert cli("refuse", str(task["id"]))[0] == 0

    import csv as csv_module

    code, out, _err = cli("export", "--format", "csv")
    assert code == 0
    rows = list(csv_module.reader(io.StringIO(out.lstrip("\ufeff"))))
    kinds = [row[1] for row in rows[1:]]
    assert kinds == ["refuse"]
    assert rows[1][4] == "Old newsletter draft"


@pytest.mark.parametrize("word", PENALTY_WORDS)
def test_no_judging_words(cli, at_time, word):
    _set_tz(cli)
    first = _add_task(cli, at_time, "Read the docs")
    second = _add_task(cli, at_time, "Call the bank")
    _add_idea(cli, at_time, "Learn to sail", why="calm")
    at_time(_noon_utc(date(2026, 9, 1)))

    combined = "\n".join(
        [
            cli("task", "list")[1],
            cli("done", str(first["id"]))[1],
            cli("refuse", str(second["id"]))[1],
            cli("aion", "list")[1],
        ]
    ).lower()
    assert word not in combined

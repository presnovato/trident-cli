"""``trident log`` / ``day`` / ``stop`` end to end, with the clock fixed."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from trident_cli import clock

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))

PENALTY_WORDS = ("%", "missed", "empty", "streak")


class TTY(io.StringIO):
    """A fake stdin that claims to be a terminal."""

    def isatty(self) -> bool:  # noqa: D102 - test double
        return True


@pytest.fixture
def at_time(monkeypatch):
    def set_time(moment: datetime):
        monkeypatch.setattr(clock, "now", lambda: moment)

    return set_time


def _set_tz(cli, value: str = "+03:00", open_hour: int = 10) -> None:
    assert cli("config", "set", "timezone", value)[0] == 0
    assert cli("config", "set", "day_open_hour", str(open_hour))[0] == 0


def _feed_input(monkeypatch, answers):
    queue = list(answers)

    def fake_input():
        if not queue:
            raise EOFError
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)


def _entries(cli, *day_args):
    return json.loads(cli("--json", "day", *day_args)[1])["entries"]


def test_log_writes_one_entry(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, err = cli("log", "Ran", "5k", "+2", "STR", "+1", "WILL")
    assert code == 0
    assert out.strip() == "Logged · STR +2 · 🟡 1"
    assert err == ""

    entry = _entries(cli)[0]
    assert entry["text"] == "Ran 5k"
    assert entry["output"] == {"str": 2, "agi": 0, "int": 0}
    assert entry["cost"] == 1
    assert entry["kind"] == "done"
    assert entry["occurred_at"] == "2026-10-02T07:41:00+00:00"
    assert entry["trident_day"] == "2026-10-02"


def test_all_zero_entry_logs_without_nagging(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, err = cli("log", "ничего особенного")
    assert code == 0
    assert out.strip() == "Logged."
    assert err == ""
    assert _entries(cli)[0]["text"] == "ничего особенного"


def test_positional_and_quoted_forms_are_equal(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    assert cli("log", "Ran", "5k", "+2", "STR")[0] == 0
    assert cli("log", "Ran 5k", "+2 STR")[0] == 0

    entries = _entries(cli)
    assert len(entries) == 2
    assert entries[0]["text"] == entries[1]["text"] == "Ran 5k"
    assert entries[0]["output"]["str"] == entries[1]["output"]["str"] == 2


def test_log_reads_piped_stdin(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", io.StringIO("Read a chapter\n+2 INT\n"))

    code, _out, err = cli("log")
    assert code == 0
    assert err == ""
    entry = _entries(cli)[0]
    assert entry["text"] == "Read a chapter"
    assert entry["output"]["int"] == 2


def test_log_reads_stdin_for_a_dash(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", io.StringIO("Read a chapter\n+2 INT\n"))

    code, _out, _err = cli("log", "-")
    assert code == 0
    entry = _entries(cli)[0]
    assert entry["text"] == "Read a chapter"
    assert entry["output"]["int"] == 2


def test_log_without_arguments_needs_a_pipe(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", TTY(""))

    code, out, err = cli("log")
    assert code == 2
    assert out == ""
    assert "nothing to log" in err


def test_parse_error_exits_two_and_writes_nothing(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, err = cli("log", "Ran", "+4", "STR")
    assert code == 2
    assert out == ""
    assert "points must be 1–3" in err
    assert _entries(cli) == []


def test_interactive_asks_and_stores_points(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", TTY(""))
    _feed_input(monkeypatch, ["2", "", "1", "3"])

    code, out, err = cli("log", "-i", "Ran", "5k")
    assert code == 0
    assert out.strip() == "Logged · STR +2 · INT +1 · 🟡 3"
    assert "Output — STR (body) 0–3 [0]:" in err
    assert "What did it cost? WILL 0–3 [0]:" in err

    entry = _entries(cli)[0]
    assert entry["text"] == "Ran 5k"
    assert entry["output"] == {"str": 2, "agi": 0, "int": 1}
    assert entry["cost"] == 3


def test_interactive_retries_invalid_input(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", TTY(""))
    _feed_input(monkeypatch, ["9", "nope", "2", "0", "0", "0"])

    code, _out, _err = cli("log", "-i", "Text")
    assert code == 0
    assert _entries(cli)[0]["output"]["str"] == 2


def test_interactive_rejects_inline_pairs(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", TTY(""))

    code, out, err = cli("log", "-i", "Ran", "+2", "STR")
    assert code == 2
    assert out == ""
    assert "use either inline attributes or -i" in err


def test_interactive_needs_a_terminal(cli, monkeypatch, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    code, out, err = cli("log", "-i", "Text")
    assert code == 2
    assert out == ""
    assert "terminal" in err


def test_entry_before_the_open_hour_lands_on_the_previous_day(cli, at_time):
    _set_tz(cli, "+03:00", 10)
    # 2026-10-03 01:30 local belongs to 2 October.
    at_time(datetime(2026, 10, 2, 22, 30, tzinfo=UTC))
    assert cli("log", "Late night")[0] == 0

    oct_2 = json.loads(cli("--json", "day", "--date", "2026-10-02")[1])
    assert [entry["text"] for entry in oct_2["entries"]] == ["Late night"]

    at_time(datetime(2026, 10, 3, 10, 0, tzinfo=UTC))
    oct_3 = json.loads(cli("--json", "day", "--date", "2026-10-03")[1])
    assert oct_3["entries"] == []


def test_changing_the_open_hour_does_not_move_an_entry(cli, at_time):
    _set_tz(cli, "+03:00", 10)
    at_time(datetime(2026, 10, 2, 22, 30, tzinfo=UTC))
    assert cli("log", "Late night")[0] == 0

    assert cli("config", "set", "day_open_hour", "0")[0] == 0

    oct_2 = json.loads(cli("--json", "day", "--date", "2026-10-02")[1])
    assert [entry["text"] for entry in oct_2["entries"]] == ["Late night"]


def test_day_shows_output_and_cost_on_separate_lines(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    cli("log", "Ran", "5k", "+2", "STR", "+1", "WILL")

    code, out, _err = cli("day")
    assert code == 0
    lines = out.splitlines()
    assert any(line.startswith("Output") and "STR 2" in line and "AGI 0" in line and "INT 0" in line for line in lines)
    assert any(line.startswith("Cost") and "🟡 1" in line for line in lines)
    assert "STR +2" in out


def test_day_json_has_output_and_cost_and_no_total(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    cli("log", "Ran", "5k", "+2", "STR", "+1", "WILL")

    payload = json.loads(cli("--json", "day")[1])
    assert set(payload) == {
        "trident_day",
        "window",
        "status",
        "rest_reason",
        "entries",
        "output",
        "cost",
    }
    assert payload["output"] == {"str": 2, "agi": 0, "int": 0}
    assert payload["cost"] == 1
    assert payload["window"]["start"] == "2026-10-02T07:00:00+00:00"
    assert payload["window"]["end"] == "2026-10-03T07:00:00+00:00"
    assert "total" not in json.dumps(payload).lower()


def test_day_yesterday_and_date(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    cli("log", "today")

    yesterday = json.loads(cli("--json", "day", "--yesterday")[1])
    assert yesterday["trident_day"] == "2026-10-01"
    assert yesterday["entries"] == []

    chosen = json.loads(cli("--json", "day", "--date", "2026-10-02")[1])
    assert [entry["text"] for entry in chosen["entries"]] == ["today"]


def test_a_future_date_is_a_usage_error(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, err = cli("day", "--date", "2099-01-01")
    assert code == 2
    assert out == ""
    assert "future" in err


def test_date_and_yesterday_together_are_a_usage_error(cli):
    code, _out, _err = cli("day", "--yesterday", "--date", "2026-10-01")
    assert code == 2


def test_a_day_without_entries_is_neutral(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, _err = cli("day")
    assert code == 0
    assert "No entries for this day." in out
    assert out.count("No entries for this day.") == 1


def test_stop_shows_a_banner_and_a_reason_label(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    code, out, _err = cli("stop", "--reason", "no-energy")
    assert code == 0
    assert out.strip() == "🌿 Rest day · no energy or wish to write"

    payload = json.loads(cli("--json", "day")[1])
    assert payload["status"] == "rest"
    assert payload["rest_reason"] == "no-energy"
    assert "🌿 Rest day · no energy or wish to write" in cli("day")[1]


def test_a_second_stop_is_a_noop(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))

    assert cli("stop")[0] == 0
    code, out, _err = cli("stop")
    assert code == 0
    assert "Already a rest day." in out
    assert len(_entries(cli)) == 1


def test_a_later_entry_turns_the_day_active(cli, at_time):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    cli("stop", "--reason", "just-because")

    at_time(datetime(2026, 10, 2, 9, 0, tzinfo=UTC))
    assert cli("log", "Did something", "+1", "INT")[0] == 0

    payload = json.loads(cli("--json", "day")[1])
    assert payload["status"] == "active"
    assert payload["rest_reason"] is None
    assert [entry["kind"] for entry in payload["entries"]] == ["stop", "done"]

    out = cli("day")[1]
    assert "🌿 rest day" in out
    assert "🌿 Rest day" not in out


@pytest.mark.parametrize("word", PENALTY_WORDS)
def test_day_never_uses_penalty_wording(cli, at_time, word):
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    cli("log", "Ran", "5k", "+2", "STR", "+1", "WILL")

    combined = (cli("day")[1] + cli("day", "--yesterday")[1]).lower()
    assert word not in combined


def test_log_decodes_piped_utf8_from_a_non_utf8_stdin(cli, monkeypatch, at_time):
    # An installed `trident` under PowerShell 5.1: stdin opens in a legacy code
    # page and the pipe may start with a byte-order mark.
    _set_tz(cli)
    at_time(datetime(2026, 10, 2, 7, 41, tzinfo=UTC))
    piped = "\ufeffПрочитал главу\n+2 РАЗУМ\n".encode("utf-8")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(piped), encoding="cp1251"))

    code, _out, err = cli("log")
    assert code == 0, err
    entry = _entries(cli)[0]
    assert entry["text"] == "Прочитал главу"
    assert entry["output"]["int"] == 2

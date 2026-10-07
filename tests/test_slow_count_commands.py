"""``trident season`` / ``history`` / ``export`` end to end, clock fixed."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import clock

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))
PENALTY_WORDS = ("%", "best", "record", "streak", "missed", "empty")


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


def _log_day(cli, at_time, day, *args) -> None:
    at_time(_noon_utc(day))
    code, _out, err = cli("log", *args)
    assert code == 0, err


def _log_points(cli, at_time, day, *, str_=0, agi=0, int_=0, will=0) -> None:
    """Log a day's points as several 1–3 point entries."""
    pairs = []
    for name, total in (("STR", str_), ("AGI", agi), ("INT", int_), ("WILL", will)):
        while total > 0:
            size = min(3, total)
            pairs.append(f"+{size} {name}")
            total -= size
    at_time(_noon_utc(day))
    for pair in pairs:
        code, _out, err = cli("log", "day", pair)
        assert code == 0, err


def _three_days(cli, at_time) -> None:
    _log_points(cli, at_time, date(2026, 9, 1), str_=25)
    _log_points(cli, at_time, date(2026, 9, 2), agi=1)
    _log_points(cli, at_time, date(2026, 9, 3), str_=11, will=1)


# --- season -----------------------------------------------------------------


def test_season_current_keeps_output_and_cost_apart(cli, at_time):
    _set_tz(cli)
    _three_days(cli, at_time)
    at_time(_noon_utc(date(2026, 9, 4)))

    code, out, err = cli("season")
    assert code == 0
    assert err == ""
    lines = out.splitlines()
    assert any(l.startswith("This season") and "STR 5" in l and "AGI 1" in l and "INT 0" in l for l in lines)
    assert any(l.startswith("Cost") and "🟡 1" in l for l in lines)
    assert any(l.startswith("Life") and "STR 0" in l for l in lines)
    assert any(l.startswith("Life cost") and "🟡 0" in l for l in lines)
    assert any("Today so far" in l for l in lines)

    payload = json.loads(cli("--json", "season")[1])
    assert payload["output"] == {"str": 5, "agi": 1, "int": 0}
    assert payload["cost"] == 1
    assert payload["base"]["output"] == {"str": 0, "agi": 0, "int": 0}
    assert payload["base"]["cost"] == 0
    assert payload["closed"] is False
    assert payload["day_number"] == 4


@pytest.mark.parametrize("word", PENALTY_WORDS)
def test_season_never_uses_penalty_wording(cli, at_time, word):
    _set_tz(cli)
    _three_days(cli, at_time)
    at_time(_noon_utc(date(2026, 9, 4)))
    assert word not in cli("season")[1].lower()


def test_season_strip_has_28_cells(cli, at_time):
    _set_tz(cli)
    _three_days(cli, at_time)
    at_time(_noon_utc(date(2026, 9, 4)))

    strip = json.loads(cli("--json", "season")[1])["strip"]
    assert len(strip) == 28
    assert set(strip) <= {"●", "~", "·"}
    assert strip[:3] == ["●", "●", "●"]
    assert strip[3] == "·"
    assert all(cell == "·" for cell in strip[4:])

    out = cli("season")[1]
    legend = next(line for line in out.splitlines() if "entries" in line)
    assert "·" not in legend


def test_season_strip_marks_a_rest_day(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 9, 1)))
    assert cli("stop")[0] == 0
    at_time(_noon_utc(date(2026, 9, 2)))

    strip = json.loads(cli("--json", "season")[1])["strip"]
    assert strip[0] == "~"


def test_season_list_and_closed_number(cli, at_time):
    _set_tz(cli)
    _three_days(cli, at_time)
    at_time(_noon_utc(date(2026, 9, 30)))  # closes 9/1..9/29; season 1 rolls

    listing = json.loads(cli("--json", "season", "--list")[1])
    assert [item["number"] for item in listing["seasons"]] == [2, 1]
    assert listing["seasons"][0]["closed"] is False
    assert listing["seasons"][1]["closed"] is True
    assert listing["seasons"][1]["output"]["str"] == 5

    current = json.loads(cli("--json", "season")[1])
    assert current["base"]["output"]["str"] == 1  # ceil(5 / 10)

    closed = json.loads(cli("--json", "season", "--number", "1")[1])
    assert closed["closed"] is True
    assert closed["output"]["str"] == 5
    assert closed["base_gain"]["output"]["str"] == 1

    out = cli("season", "--number", "1")[1]
    assert "To life" in out
    assert "closed" in out

    lines = cli("season", "--list")[1].splitlines()
    assert lines[0].endswith("· open")
    assert "STR 5" in lines[1]


def test_season_unknown_number_and_conflicting_flags(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 9, 4)))

    code, out, err = cli("season", "--number", "99")
    assert code == 2
    assert out == ""
    assert "unknown season" in err

    code, _out, _err = cli("season", "--number", "1", "--list")
    assert code == 2


# --- history ----------------------------------------------------------------


def test_history_default_is_seven_days(cli, at_time):
    _set_tz(cli)
    _log_day(cli, at_time, date(2026, 10, 1), "One", "+1", "STR")
    _log_day(cli, at_time, date(2026, 10, 2), "Two", "+1", "AGI")
    at_time(_noon_utc(date(2026, 10, 2)))

    payload = json.loads(cli("--json", "history")[1])
    assert payload["until"] == "2026-10-02"
    assert payload["since"] == "2026-09-26"
    assert [day["trident_day"] for day in payload["days"]] == ["2026-10-02", "2026-10-01"]

    out = cli("history")[1]
    assert "Output STR 1 · AGI 0 · INT 0 · 🟡 0" in out


def test_history_since_forms(cli, at_time):
    _set_tz(cli)
    _log_day(cli, at_time, date(2026, 10, 1), "One", "+1", "STR")
    _log_day(cli, at_time, date(2026, 10, 2), "Two", "+1", "AGI")
    at_time(_noon_utc(date(2026, 10, 2)))

    assert json.loads(cli("--json", "history", "--since", "30d")[1])["since"] == "2026-09-03"
    dated = json.loads(cli("--json", "history", "--since", "2026-10-02")[1])
    assert [day["trident_day"] for day in dated["days"]] == ["2026-10-02"]

    every = json.loads(cli("--json", "history", "--since", "all")[1])
    assert every["since"] is None
    assert [day["trident_day"] for day in every["days"]] == ["2026-10-02", "2026-10-01"]


def test_history_bad_values_and_order(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 2)))

    for bad in ("soon", "0d", "-1d", "2026/10/02"):
        code, _out, err = cli("history", "--since", bad)
        assert code == 2, bad
        assert err != ""

    assert cli("history", "--until", "nonsense")[0] == 2
    assert cli("history", "--since", "2026-10-05", "--until", "2026-10-01")[0] == 2


def test_history_empty_range(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 2)))

    code, out, _err = cli("history", "--since", "2000-01-01", "--until", "2000-01-31")
    assert code == 0
    assert "No entries in this range." in out


def test_history_rest_day_and_untouched_days_skipped(cli, at_time):
    _set_tz(cli)
    _log_day(cli, at_time, date(2026, 10, 1), "One", "+1", "STR")
    at_time(_noon_utc(date(2026, 10, 2)))
    assert cli("stop", "--reason", "unwell")[0] == 0
    at_time(_noon_utc(date(2026, 10, 3)))

    out = cli("history")[1]
    assert "🌿 Rest day · not feeling well" in out

    payload = json.loads(cli("--json", "history")[1])
    assert [day["trident_day"] for day in payload["days"]] == ["2026-10-02", "2026-10-01"]


# --- export -----------------------------------------------------------------


def test_export_json_shape(cli, at_time):
    _set_tz(cli)
    _log_day(cli, at_time, date(2026, 10, 1), "Ran", "+2", "STR")
    at_time(_noon_utc(date(2026, 10, 2)))

    code, out, err = cli("export")
    assert code == 0
    assert err == ""

    payload = json.loads(out)
    assert payload["format_version"] == 1
    assert payload["settings"] == {"timezone": "+03:00", "day_open_hour": 10}
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["text"] == "Ran"
    assert payload["closed_days"][0]["trident_day"] == "2026-10-01"
    assert payload["closed_days"][0]["gains"]["output"]["str"] == 1
    assert payload["seasons"][0]["number"] == 1
    assert payload["seasons"][0]["base_gain"] is None


def test_export_ignores_the_json_flag(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 1)))
    assert cli("log", "x")[0] == 0

    code, out, _err = cli("--json", "export")
    assert code == 0
    assert json.loads(out)["format_version"] == 1


def test_export_csv_has_a_bom_and_round_trips(cli, at_time):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 1)))
    assert cli("log", "Привет", "мир", "+1", "INT")[0] == 0
    assert cli("log", "Line one\nLine two")[0] == 0
    at_time(_noon_utc(date(2026, 10, 2)))

    code, out, err = cli("export", "--format", "csv")
    assert code == 0
    assert err == ""
    assert out.startswith("\ufeff")

    rows = list(csv.reader(io.StringIO(out.lstrip("\ufeff"))))
    assert rows[0] == ["uid", "kind", "trident_day", "occurred_at", "text", "str", "agi", "int", "will", "stop_reason"]
    texts = [row[4] for row in rows[1:]]
    assert "Привет мир" in texts
    assert "Line one\nLine two" in texts


def test_export_output_file_refuses_to_overwrite(cli, at_time, tmp_path):
    _set_tz(cli)
    at_time(_noon_utc(date(2026, 10, 1)))
    assert cli("log", "x")[0] == 0

    target = tmp_path / "journal.csv"
    code, out, err = cli("export", "--format", "csv", "--output", str(target))
    assert code == 0
    assert out == ""
    assert "Exported 1 entries" in err
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")

    code, _out, err = cli("export", "--format", "csv", "--output", str(target))
    assert code == 2
    assert "exists" in err

    code, _out, _err = cli("export", "--format", "csv", "--output", str(target), "--force")
    assert code == 0

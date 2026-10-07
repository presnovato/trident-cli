"""Local configuration defaults and validation."""

from __future__ import annotations

import json
import sqlite3

from trident_cli import paths


def _list_json(cli):
    code, out, _err = cli("--json", "config", "list")
    assert code == 0
    return {item["key"]: item for item in json.loads(out)}


def test_defaults_are_present(cli):
    settings = _list_json(cli)
    assert set(settings) == {"timezone", "day_open_hour"}
    assert settings["day_open_hour"]["value"] == 10
    assert settings["day_open_hour"]["source"] == "default"


def test_set_get_unset_round_trip(cli):
    code, _out, _err = cli("config", "set", "day_open_hour", "9")
    assert code == 0

    code, out, _err = cli("config", "get", "day_open_hour")
    assert code == 0
    assert out.strip() == "9"

    settings = _list_json(cli)
    assert settings["day_open_hour"]["source"] == "stored"

    code, _out, _err = cli("config", "unset", "day_open_hour")
    assert code == 0

    code, out, _err = cli("config", "get", "day_open_hour")
    assert code == 0
    assert out.strip() == "10"

    settings = _list_json(cli)
    assert settings["day_open_hour"]["source"] == "default"


def test_value_survives_a_new_connection(cli):
    assert cli("config", "set", "day_open_hour", "7")[0] == 0
    # A fresh sqlite3 connection reads what was stored.
    conn = sqlite3.connect(str(paths.db_path()))
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'day_open_hour'").fetchone()
        assert row[0] == "7"
    finally:
        conn.close()


def test_get_unknown_key_is_a_usage_error(cli):
    code, _out, err = cli("config", "get", "nope")
    assert code == 2
    assert "unknown setting" in err


def test_set_unknown_key_is_a_usage_error(cli):
    code, _out, err = cli("config", "set", "nope", "x")
    assert code == 2
    assert "unknown setting" in err


def test_invalid_day_open_hour(cli):
    for value in ("-1", "24", "ten"):
        code, _out, err = cli("config", "set", "day_open_hour", value)
        assert code == 2, value
        assert "day_open_hour" in err


def test_invalid_timezone(cli):
    code, _out, err = cli("config", "set", "timezone", "Not/AZone")
    assert code == 2
    assert "timezone" in err


def test_timezone_utc_is_accepted(cli):
    assert cli("config", "set", "timezone", "UTC")[0] == 0








def test_fixed_offset_timezone_is_accepted(cli):
    assert cli("config", "set", "timezone", "+03:00")[0] == 0
    assert cli("config", "get", "timezone")[1].strip() == "+03:00"


def test_default_timezone_falls_back_to_system_offset(monkeypatch):
    from trident_cli import settings

    def no_tz_database(_name):
        raise settings.ZoneInfoNotFoundError("no tz database")

    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(settings, "ZoneInfo", no_tz_database)

    assert settings._default_timezone() == settings.system_offset()


def test_system_offset_format():
    import re
    from datetime import timedelta

    from trident_cli import settings

    assert re.fullmatch(r"[+-]\d{2}:\d{2}", settings.system_offset())
    assert settings.format_offset(timedelta(hours=3)) == "+03:00"
    assert settings.format_offset(timedelta(hours=-5, minutes=-30)) == "-05:30"
    assert settings.format_offset(timedelta(0)) == "+00:00"


def test_to_tzinfo_handles_offsets_utc_and_unknown_names(monkeypatch):
    from datetime import datetime, timedelta

    import pytest

    from trident_cli import settings

    moment = datetime(2026, 10, 2, 12, 0)
    assert settings.to_tzinfo("+03:00").utcoffset(moment) == timedelta(hours=3)
    assert settings.to_tzinfo("UTC").utcoffset(moment) == timedelta(0)

    def no_tz_database(_name):
        raise settings.ZoneInfoNotFoundError("no tz database")

    monkeypatch.setattr(settings, "ZoneInfo", no_tz_database)
    with pytest.raises(ValueError):
        settings.to_tzinfo("Europe/Moscow")


def test_user_tzinfo_reads_the_stored_setting(cli):
    from datetime import datetime, timedelta

    from trident_cli import settings, storage

    assert cli("config", "set", "timezone", "+05:30")[0] == 0
    conn = storage.connect()
    try:
        tz = settings.user_tzinfo(conn)
    finally:
        conn.close()
    assert tz.utcoffset(datetime(2026, 10, 2)) == timedelta(hours=5, minutes=30)

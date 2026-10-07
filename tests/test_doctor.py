"""Local diagnostics for trident-cli."""

from __future__ import annotations

import json


def test_doctor_reports_local_runtime_and_data_path(cli):
    code, out, err = cli("doctor")
    assert code == 0
    assert err == ""
    assert "trident-cli: 0.1.0" in out
    assert "Кириллица и 🟡" in out
    assert "data directory:" in out
    assert "schema version:" in out


def test_doctor_json_parses_and_reports_settings(cli):
    code, out, _err = cli("--json", "doctor")
    assert code == 0
    data = json.loads(out)
    assert data["trident-cli"] == "0.1.0"
    assert data["pending migrations"] == 0
    assert data["data directory writable"] == "yes"
    assert "timezone" in data
    assert "day open hour" in data


def test_doctor_flags_a_guessed_timezone(cli):
    data = json.loads(cli("--json", "doctor")[1])
    assert data["timezone source"] == "default"
    assert "timezone note" in data

    cli("config", "set", "timezone", "+03:00")
    data = json.loads(cli("--json", "doctor")[1])
    assert data["timezone source"] == "stored"
    assert "timezone note" not in data

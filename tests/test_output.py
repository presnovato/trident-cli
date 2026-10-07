"""Output conventions: valid JSON that keeps non-ASCII characters readable."""

from __future__ import annotations

import json


def test_json_is_valid_and_keeps_unicode(cli):
    code, out, _err = cli("--json", "doctor")
    assert code == 0
    data = json.loads(out)
    assert "Кириллица" in json.dumps(data, ensure_ascii=False)
    # The raw bytes must carry the characters, not \uXXXX escapes.
    assert "Кириллица" in out
    assert "🟡" in out
    assert "\\u" not in out


def test_errors_go_to_stderr_not_stdout(cli):
    code, out, err = cli("config", "get", "no_such_key")
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_json_flag_works_after_the_subcommand(cli):
    code, out, _err = cli("doctor", "--json")
    assert code == 0
    assert json.loads(out)["trident-cli"] == "0.1.0"

    code, out, _err = cli("config", "list", "--json")
    assert code == 0
    assert {item["key"] for item in json.loads(out)} == {"timezone", "day_open_hour"}


def test_json_flag_still_works_before_the_subcommand(cli):
    code, out, _err = cli("--json", "doctor")
    assert code == 0
    assert json.loads(out)["trident-cli"] == "0.1.0"

"""The command map: version, help and dispatch."""

from __future__ import annotations

COMMANDS = (
    "doctor",
    "config",
    "log",
    "day",
    "stop",
    "season",
    "history",
    "export",
    "task",
    "done",
    "refuse",
    "aion",
)


def test_version(cli):
    code, out, err = cli("--version")
    assert code == 0
    assert out.strip() == "trident-cli 0.1.0"
    assert err == ""


def test_no_args_prints_help(cli):
    code, out, err = cli()
    assert code == 0
    assert "usage:" in out


def test_help_lists_every_command(cli):
    code, out, _err = cli("--help")
    assert code == 0
    for name in COMMANDS:
        assert name in out


def test_unknown_command_is_a_usage_error(cli):
    code, _out, err = cli("nonsense")
    assert code == 2
    assert "invalid choice" in err

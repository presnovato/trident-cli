"""Shared fixtures: an isolated data directory and a CLI runner."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Point the CLI at a temporary data directory for each test."""
    monkeypatch.setenv("TRIDENT_HOME", str(tmp_path / "trident-home"))
    yield


@pytest.fixture
def cli(capsys):
    """Call ``main(argv)`` and return ``(exit_code, stdout, stderr)``."""
    from trident_cli.__main__ import main

    def run(*argv: str):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run

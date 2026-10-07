"""SQLite schema setup and upgrade guard."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from trident_cli import paths, plan, storage
from trident_cli.errors import CliError
from trident_cli.storage.migrations import LATEST


def test_fresh_database_reaches_latest_version():
    conn = storage.connect()
    try:
        assert storage.current_version(conn) == LATEST
        assert storage.pending(conn) == 0
    finally:
        conn.close()


def test_reconnect_applies_nothing():
    first = storage.connect()
    version = storage.current_version(first)
    first.close()

    second = storage.connect()
    try:
        assert storage.current_version(second) == version
        assert storage.pending(second) == 0
    finally:
        second.close()


def test_local_tables_exist():
    conn = storage.connect()
    try:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"settings", "entries", "seasons", "closed_days", "tasks", "aion", "task_steps"} <= tables
    finally:
        conn.close()


def test_v7_task_strategy_link_remains_usable(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = storage.connect(db_path)
    conn.execute("ALTER TABLE tasks RENAME COLUMN strategy_id TO strategy_server_id")
    conn.execute("PRAGMA user_version = 7")
    conn.commit()
    conn.close()

    conn = storage.connect(db_path)
    try:
        now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)
        task = plan.add_task(
            conn,
            text="Keep this task",
            now=now,
            tz=timezone.utc,
            open_hour=10,
            strategy_kind="epic",
            strategy_id=3,
            strategy_title="Local link",
        )
        assert task["strategy"] == {"kind": "epic", "id": 3, "title": "Local link"}
    finally:
        conn.close()


def test_newer_schema_raises_upgrade_error():
    conn = storage.connect()
    conn.close()

    raw = sqlite3.connect(str(paths.db_path()))
    raw.execute(f"PRAGMA user_version = {LATEST + 1}")
    raw.commit()
    raw.close()

    with pytest.raises(CliError) as excinfo:
        storage.connect()
    assert "newer trident-cli" in excinfo.value.message
    assert excinfo.value.code == 1

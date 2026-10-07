"""SQLite schema for the standalone local Trident journal."""

from __future__ import annotations

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        8,
        "local core",
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entries (
            id           INTEGER PRIMARY KEY,
            uid          TEXT    NOT NULL UNIQUE,
            kind         TEXT    NOT NULL CHECK (kind IN ('done', 'stop', 'refuse')),
            text         TEXT    NOT NULL,
            str_points   INTEGER NOT NULL DEFAULT 0 CHECK (str_points  BETWEEN 0 AND 3),
            agi_points   INTEGER NOT NULL DEFAULT 0 CHECK (agi_points  BETWEEN 0 AND 3),
            int_points   INTEGER NOT NULL DEFAULT 0 CHECK (int_points  BETWEEN 0 AND 3),
            will_points  INTEGER NOT NULL DEFAULT 0 CHECK (will_points BETWEEN 0 AND 3),
            stop_reason  TEXT,
            occurred_at  TEXT    NOT NULL,
            trident_day  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS entries_trident_day
            ON entries (trident_day, occurred_at);

        CREATE TABLE IF NOT EXISTS seasons (
            number      INTEGER PRIMARY KEY,
            start_day   TEXT    NOT NULL UNIQUE,
            closed_at   TEXT,
            str_gain    INTEGER,
            agi_gain    INTEGER,
            int_gain    INTEGER,
            will_gain   INTEGER
        );

        CREATE TABLE IF NOT EXISTS closed_days (
            trident_day   TEXT    PRIMARY KEY,
            season_number INTEGER NOT NULL REFERENCES seasons (number),
            str_total     INTEGER NOT NULL,
            agi_total    INTEGER NOT NULL,
            int_total    INTEGER NOT NULL,
            will_total   INTEGER NOT NULL,
            str_gain     INTEGER NOT NULL,
            agi_gain     INTEGER NOT NULL,
            int_gain     INTEGER NOT NULL,
            will_gain    INTEGER NOT NULL,
            closed_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY,
            uid           TEXT    NOT NULL UNIQUE,
            text          TEXT    NOT NULL,
            status        TEXT    NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'done', 'refused', 'moved', 'consumed')),
            created_at    TEXT    NOT NULL,
            created_day   TEXT    NOT NULL,
            closed_at     TEXT,
            entry_uid     TEXT,
            aion_id       INTEGER,
            task_date     TEXT,
            note          TEXT,
            remind_at     TEXT,
            is_frog       INTEGER NOT NULL DEFAULT 0,
            below_line    INTEGER NOT NULL DEFAULT 0,
            strategy_kind TEXT,
            strategy_id   INTEGER,
            strategy_title TEXT,
            steps_mode    TEXT    NOT NULL DEFAULT 'free'
        );
        CREATE INDEX IF NOT EXISTS tasks_status ON tasks (status, id);

        CREATE TABLE IF NOT EXISTS aion (
            id         INTEGER PRIMARY KEY,
            uid        TEXT    NOT NULL UNIQUE,
            text       TEXT    NOT NULL,
            why        TEXT,
            status     TEXT    NOT NULL DEFAULT 'open'
                       CHECK (status IN ('open', 'pulled', 'dropped')),
            created_at TEXT    NOT NULL,
            closed_at TEXT,
            task_id    INTEGER,
            note       TEXT
        );
        CREATE INDEX IF NOT EXISTS aion_status ON aion (status, created_at, id);

        CREATE TABLE IF NOT EXISTS task_steps (
            id         INTEGER PRIMARY KEY,
            uid        TEXT    NOT NULL UNIQUE,
            owner_kind TEXT    NOT NULL CHECK (owner_kind IN ('task', 'aion')),
            owner_uid  TEXT    NOT NULL,
            step_order INTEGER NOT NULL,
            text       TEXT    NOT NULL,
            is_done    INTEGER NOT NULL DEFAULT 0,
            is_skipped INTEGER NOT NULL DEFAULT 0,
            entry_uid  TEXT,
            is_removed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS task_steps_owner
            ON task_steps (owner_kind, owner_uid, step_order, id);
        """,
    ),
]

LATEST: int = MIGRATIONS[-1][0]

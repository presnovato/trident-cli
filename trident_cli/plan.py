"""Data access for the plan axis: Chronos (tasks) and Aion (ideas).

A task's status and its journal entry are written in one transaction. Capacity
is per Trident day: at most six open dated tasks on one day. Underline tasks
float and do not count. The plan helps, it does not judge. Every task field and
step is stored locally.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import date, datetime, timezone, tzinfo

from trident_cli import days, journal
from trident_cli.errors import EXIT_USAGE, CliError

MAX_TASKS_PER_DAY = 6
MAX_OPEN_TASKS = MAX_TASKS_PER_DAY  # kept for callers that only need the number
PLAN_FULL = (
    "The day already holds 6 open tasks. "
    "Finish one, let one go, or move it to another day."
)

_ID_RE = re.compile(r"#?(\d+)")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")

STRATEGY_KINDS = ("epic", "sprint")


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_id(raw: str) -> int:
    """Accept ``12`` or ``#12`` and return the integer id."""
    match = _ID_RE.fullmatch(str(raw).strip())
    if match is None or int(match.group(1)) < 1:
        raise CliError(f"not an id: {raw}", code=EXIT_USAGE)
    return int(match.group(1))


def parse_date(raw: str) -> date:
    """A ``YYYY-MM-DD`` Trident day, or a usage error."""
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError as exc:
        raise CliError(f"not a date: {raw}", code=EXIT_USAGE) from exc


def parse_remind(raw: str) -> str:
    """``HH:MM`` in 24-hour form, or a usage error."""
    match = _TIME_RE.fullmatch(str(raw).strip())
    if match is None:
        raise CliError(f"not a time: {raw}", code=EXIT_USAGE)
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise CliError(f"not a time: {raw}", code=EXIT_USAGE)
    return f"{hour:02d}:{minute:02d}"


def parse_strategy_id(raw: str) -> int:
    text = str(raw).strip().lstrip("#")
    if not text.isdigit() or int(text) < 1:
        raise CliError(f"not an id: {raw}", code=EXIT_USAGE)
    return int(text)


# --- reads ------------------------------------------------------------------


def open_count(conn: sqlite3.Connection) -> int:
    """Every open task, whatever the day."""
    return conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE status = 'pending'"
    ).fetchone()["c"]


def day_open_count(conn: sqlite3.Connection, day: date) -> int:
    """Open dated tasks on one Trident day."""
    return conn.execute(
        "SELECT COUNT(*) AS c FROM tasks "
        "WHERE status = 'pending' AND below_line = 0 AND task_date = ?",
        (day.isoformat(),),
    ).fetchone()["c"]


def get_open_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM tasks WHERE id = ? AND status = 'pending'", (task_id,)
    ).fetchone()
    if row is None:
        raise CliError(f"no open task #{task_id}", code=1)
    return row


def get_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    """Any task by id, open or closed — the read side of ``task show``."""
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise CliError(f"no task #{task_id}", code=1)
    return row


def get_open_idea(conn: sqlite3.Connection, idea_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM aion WHERE id = ? AND status = 'open'", (idea_id,)
    ).fetchone()
    if row is None:
        raise CliError(f"no idea #{idea_id} in Aion", code=1)
    return row


def steps_for(conn: sqlite3.Connection, owner_kind: str, owner_uid: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM task_steps WHERE owner_kind = ? AND owner_uid = ? AND is_removed = 0 "
        "ORDER BY step_order, id",
        (owner_kind, owner_uid),
    ).fetchall()
    return [_step_json(row) for row in rows]


def _step_json(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "uid": row["uid"],
        "order": row["step_order"],
        "text": row["text"],
        "is_done": bool(row["is_done"]),
        "is_skipped": bool(row["is_skipped"]),
    }


def _strategy_column(conn: sqlite3.Connection) -> str:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    return "strategy_id" if "strategy_id" in columns else "strategy_server_id"


def _strategy_json(row: sqlite3.Row) -> dict | None:
    if row["strategy_kind"] is None:
        return None
    columns = row.keys()
    identifier = row["strategy_id"] if "strategy_id" in columns else row["strategy_server_id"]
    return {
        "kind": row["strategy_kind"],
        "id": identifier,
        "title": row["strategy_title"],
    }


def _task_json(conn: sqlite3.Connection, row: sqlite3.Row, entry: dict | None = None) -> dict:
    if entry is None and row["entry_uid"]:
        entry = journal.entry_by_uid(conn, row["entry_uid"])
    return {
        "id": row["id"],
        "uid": row["uid"],
        "text": row["text"],
        "status": row["status"],
        "created_at": row["created_at"],
        "created_day": row["created_day"],
        "closed_at": row["closed_at"],
        "from_aion": row["aion_id"],
        "entry": entry,
        "task_date": row["task_date"],
        "note": row["note"],
        "remind_at": row["remind_at"],
        "is_frog": bool(row["is_frog"]),
        "below_line": bool(row["below_line"]),
        "strategy": _strategy_json(row),
        "steps": steps_for(conn, "task", row["uid"]),
        "steps_mode": row["steps_mode"],
    }


def _idea_json(row: sqlite3.Row, steps: list[dict] | None = None) -> dict:
    return {
        "id": row["id"],
        "uid": row["uid"],
        "text": row["text"],
        "why": row["why"],
        "note": row["note"],
        "status": row["status"],
        "created_at": row["created_at"],
        "steps": steps or [],
    }


def open_tasks(conn: sqlite3.Connection, current_day: date) -> dict:
    """Open tasks grouped by how they relate to the chosen Trident day."""
    rows = conn.execute("SELECT * FROM tasks WHERE status = 'pending' ORDER BY id").fetchall()
    today = current_day.isoformat()
    plan, earlier, later, underline = [], [], [], []
    for row in rows:
        task = _task_json(conn, row)
        if row["below_line"]:
            underline.append(task)
            continue
        task_day = row["task_date"]
        if task_day == today:
            plan.append(task)
        elif task_day is not None and task_day < today:
            earlier.append(task)
        else:
            later.append(task)
    return {
        "plan": plan,
        "from_earlier": earlier,
        "underline": underline,
        "later": later,
        "date": today,
    }


def done_today(conn: sqlite3.Connection, current_day: date, tz: tzinfo, open_hour: int) -> list[dict]:
    """Tasks closed during the current Trident day, in closing order."""
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status IN ('done', 'refused') AND closed_at IS NOT NULL "
        "ORDER BY closed_at, id"
    ).fetchall()
    result = []
    for row in rows:
        closed = days.trident_day(datetime.fromisoformat(row["closed_at"]), tz, open_hour)
        if closed == current_day:
            result.append(_task_json(conn, row))
    return result


# --- local helpers ----------------------------------------------------------






def _insert_steps(conn: sqlite3.Connection, owner_kind: str, owner_uid: str, texts: list[str]) -> None:
    for index, text in enumerate(texts, start=1):
        conn.execute(
            "INSERT INTO task_steps (uid, owner_kind, owner_uid, step_order, text) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), owner_kind, owner_uid, index, text),
        )




# --- writes -----------------------------------------------------------------


def add_task(
    conn: sqlite3.Connection,
    *,
    text: str,
    now: datetime,
    tz: tzinfo,
    open_hour: int,
    task_date: date | None = None,
    note: str | None = None,
    remind_at: str | None = None,
    is_frog: bool = False,
    below_line: bool = False,
    strategy_kind: str | None = None,
    strategy_id: int | None = None,
    strategy_title: str | None = None,
    steps: list[str] | None = None,
    steps_mode: str = "free",
) -> dict:
    if below_line and is_frog:
        raise CliError("a frog is a dated task, not an Underline task", code=EXIT_USAGE)
    if task_date is None and not below_line:
        task_date = days.trident_day(now, tz, open_hour)
    if below_line:
        task_date = None
    elif day_open_count(conn, task_date) >= MAX_TASKS_PER_DAY:
        raise CliError(PLAN_FULL, code=1)

    uid = str(uuid.uuid4())
    strategy_column = _strategy_column(conn)
    with conn:
        conn.execute(
            "INSERT INTO tasks "
            "(uid, text, status, created_at, created_day, task_date, note, remind_at, "
            f" is_frog, below_line, strategy_kind, {strategy_column}, strategy_title, steps_mode) "
            "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uid,
                text,
                _iso_utc(now),
                days.trident_day(now, tz, open_hour).isoformat(),
                task_date.isoformat() if task_date is not None else None,
                note,
                remind_at,
                1 if is_frog else 0,
                1 if below_line else 0,
                strategy_kind,
                strategy_id,
                strategy_title,
                steps_mode,
            ),
        )
        if steps:
            _insert_steps(conn, "task", uid, steps)
    row = conn.execute("SELECT * FROM tasks WHERE uid = ?", (uid,)).fetchone()
    return _task_json(conn, row)


def edit_task(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    now: datetime,
    text: str | None = None,
    note: str | None = None,
    remind_at: str | None = None,
    task_date: date | None = None,
    below_line: bool | None = None,
    is_frog: bool | None = None,
    strategy_kind: str | None = None,
    strategy_id: int | None = None,
    strategy_title: str | None = None,
    clear_strategy: bool = False,
    default_day: date | None = None,
) -> dict:
    """Apply the named changes; an omitted field is left untouched.

    ``note``/``remind_at`` set to an empty string clear the value; ``None``
    means "not changed". Use :func:`clear_strategy` to unlink a Strategy.
    """
    row = get_open_task(conn, task_id)
    uid = row["uid"]
    current_below = bool(row["below_line"])
    current_day = row["task_date"]

    update_fields: dict = {}
    if text is not None and text != row["text"]:
        update_fields["text"] = text
    if note is not None and note != (row["note"] or ""):
        update_fields["note"] = note or None
    if remind_at is not None and remind_at != (row["remind_at"] or ""):
        update_fields["remind_at"] = remind_at or None

    # --- placement ---------------------------------------------------------
    if below_line is True:
        target_below, target_day = True, None
    elif below_line is False:
        target_below = False
        target_day = task_date.isoformat() if task_date is not None else (
            default_day.isoformat() if default_day is not None else current_day
        )
    elif task_date is not None:
        target_below, target_day = False, task_date.isoformat()
    else:
        target_below, target_day = current_below, current_day

    if target_below:
        target_day = None
    ended_up_dated = not target_below
    if ended_up_dated:
        was_on_target = (not current_below) and current_day == target_day
        if not was_on_target and day_open_count(conn, date.fromisoformat(target_day)) >= MAX_TASKS_PER_DAY:
            raise CliError(PLAN_FULL, code=1)

    effective_frog = bool(row["is_frog"]) if is_frog is None else is_frog
    if target_below:
        if is_frog:
            raise CliError("a frog is a dated task, not an Underline task", code=EXIT_USAGE)
        effective_frog = False
    if effective_frog != bool(row["is_frog"]):
        update_fields["is_frog"] = effective_frog

    strategy_change = clear_strategy or strategy_kind is not None

    with conn:
        assignments = []
        values: list = []
        for field, column in (
            ("text", "text"),
            ("note", "note"),
            ("remind_at", "remind_at"),
            ("is_frog", "is_frog"),
        ):
            if field in update_fields:
                assignments.append(f"{column} = ?")
                value = update_fields[field]
                values.append(1 if field == "is_frog" and value else value)
        if ended_up_dated != (not current_below) or (ended_up_dated and target_day != current_day):
            assignments.append("below_line = ?")
            values.append(1 if target_below else 0)
            assignments.append("task_date = ?")
            values.append(target_day)
        if strategy_change:
            assignments.append("strategy_kind = ?")
            values.append(None if clear_strategy else strategy_kind)
            assignments.append(f"{_strategy_column(conn)} = ?")
            values.append(None if clear_strategy else strategy_id)
            assignments.append("strategy_title = ?")
            values.append(None if clear_strategy else strategy_title)
        if assignments:
            values.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?", values)

    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, row)


def move_task(conn: sqlite3.Connection, *, task_id: int, target_date: date, now: datetime) -> dict:
    return edit_task(conn, task_id=task_id, now=now, task_date=target_date)


# --- steps ------------------------------------------------------------------


def add_step(conn: sqlite3.Connection, *, task_id: int, text: str, now: datetime) -> dict:
    row = get_open_task(conn, task_id)
    uid = row["uid"]
    step_uid = str(uuid.uuid4())
    with conn:
        top = conn.execute(
            "SELECT COALESCE(MAX(step_order), 0) AS m FROM task_steps "
            "WHERE owner_kind = 'task' AND owner_uid = ? AND is_removed = 0",
            (uid,),
        ).fetchone()["m"]
        conn.execute(
            "INSERT INTO task_steps (uid, owner_kind, owner_uid, step_order, text) "
            "VALUES (?, 'task', ?, ?, ?)",
            (step_uid, uid, top + 1, text),
        )
    changed = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, changed)


def remove_step(conn: sqlite3.Connection, *, task_id: int, order: int, now: datetime) -> dict:
    row = get_open_task(conn, task_id)
    uid = row["uid"]
    step = conn.execute(
        "SELECT * FROM task_steps WHERE owner_kind = 'task' AND owner_uid = ? "
        "AND step_order = ? AND is_removed = 0",
        (uid, order),
    ).fetchone()
    if step is None:
        raise CliError(f"no step {order} on task #{task_id}", code=1)
    if step["is_done"] or step["is_skipped"] or step["entry_uid"]:
        raise CliError(
            f"step {order} already has progress; it cannot be removed", code=1
        )

    with conn:
        conn.execute("UPDATE task_steps SET is_removed = 1 WHERE id = ?", (step["id"],))
        conn.execute(
            "UPDATE task_steps SET step_order = step_order - 1 "
            "WHERE owner_kind = 'task' AND owner_uid = ? AND is_removed = 0 "
            "AND step_order > ?",
            (uid, step["step_order"]),
        )
    changed = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, changed)


def set_step(conn: sqlite3.Connection, *, task_id: int, order: int, action: str, now: datetime) -> dict:
    row = get_open_task(conn, task_id)
    uid = row["uid"]
    step = conn.execute(
        "SELECT * FROM task_steps WHERE owner_kind = 'task' AND owner_uid = ? "
        "AND step_order = ? AND is_removed = 0",
        (uid, order),
    ).fetchone()
    if step is None:
        raise CliError(f"no step {order} on task #{task_id}", code=1)
    if action not in ("complete", "skip", "resume"):
        raise CliError(f"not a step action: {action}", code=EXIT_USAGE)

    if action == "complete":
        is_done, is_skipped = 1, 0
    elif action == "skip":
        is_done, is_skipped = 0, 1
    else:
        is_done, is_skipped = 0, 0

    with conn:
        conn.execute(
            "UPDATE task_steps SET is_done = ?, is_skipped = ? WHERE id = ?",
            (is_done, is_skipped, step["id"]),
        )
    changed = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, changed)


def subtask(
    conn: sqlite3.Connection, *, child_id: int, parent_id: int, now: datetime
) -> tuple[dict, dict, dict]:
    """Turn a pending child task into a step of a parent task, atomically.

    Both tasks must be pending dated Chronos tasks on the same day,
    neither may already have steps, and the child cannot be its own parent.
    """
    child = get_open_task(conn, child_id)
    parent = get_open_task(conn, parent_id)
    if child_id == parent_id:
        raise CliError("a task cannot be its own parent", code=EXIT_USAGE)
    if child["below_line"] or parent["below_line"]:
        raise CliError("both tasks must be dated Chronos tasks", code=EXIT_USAGE)
    if child["task_date"] != parent["task_date"]:
        raise CliError("both tasks must be on the same day", code=EXIT_USAGE)
    child_steps = steps_for(conn, "task", child["uid"])
    parent_steps = steps_for(conn, "task", parent["uid"])
    if child_steps or parent_steps:
        raise CliError("neither task may already have steps", code=EXIT_USAGE)

    step_uid = str(uuid.uuid4())
    order = len(parent_steps) + 1
    with conn:
        conn.execute(
            "INSERT INTO task_steps (uid, owner_kind, owner_uid, step_order, text) "
            "VALUES (?, 'task', ?, ?, ?)",
            (step_uid, parent["uid"], order, child["text"]),
        )
        conn.execute(
            "UPDATE tasks SET status = 'consumed', closed_at = ? WHERE id = ?",
            (_iso_utc(now), child_id),
        )
    child_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (child_id,)).fetchone()
    parent_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (parent_id,)).fetchone()
    step_row = conn.execute("SELECT * FROM task_steps WHERE uid = ?", (step_uid,)).fetchone()
    return (
        _task_json(conn, child_row),
        _task_json(conn, parent_row),
        _step_json(step_row),
    )



# --- completion and refusal -------------------------------------------------


def complete_task(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    str_points: int = 0,
    agi_points: int = 0,
    int_points: int = 0,
    will_points: int = 0,
    now: datetime,
    tz: tzinfo,
    open_hour: int,
    silent: bool = False,
) -> dict:
    row = get_open_task(conn, task_id)
    entry = None
    with conn:
        if not silent:
            entry = journal.insert_entry(
                conn,
                kind="done",
                text=row["text"],
                occurred_at=now,
                tz=tz,
                open_hour=open_hour,
                str_points=str_points,
                agi_points=agi_points,
                int_points=int_points,
                will_points=will_points,
                )
        conn.execute(
            "UPDATE tasks SET status = 'done', closed_at = ?, entry_uid = ? WHERE id = ?",
            (_iso_utc(now), entry["uid"] if entry else None, task_id),
        )
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, row, entry)


def refuse_task(
    conn: sqlite3.Connection, *, task_id: int, now: datetime, tz: tzinfo, open_hour: int
) -> dict:
    row = get_open_task(conn, task_id)
    with conn:
        entry = journal.insert_entry(
            conn,
            kind="refuse",
            text=row["text"],
            occurred_at=now,
            tz=tz,
            open_hour=open_hour,
        )
        conn.execute(
            "UPDATE tasks SET status = 'refused', closed_at = ?, entry_uid = ? WHERE id = ?",
            (_iso_utc(now), entry["uid"], task_id),
        )
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_json(conn, row, entry)


# --- Aion -------------------------------------------------------------------


def move_to_aion(conn: sqlite3.Connection, *, task_id: int, now: datetime) -> tuple[dict, dict]:
    row = get_open_task(conn, task_id)
    uid = str(uuid.uuid4())
    with conn:
        cursor = conn.execute(
            "INSERT INTO aion (uid, text, why, note, status, created_at) "
            "VALUES (?, ?, NULL, ?, 'open', ?)",
            (uid, row["text"], row["note"], _iso_utc(now)),
        )
        idea_id = cursor.lastrowid
        conn.execute(
            "UPDATE tasks SET status = 'moved', closed_at = ? WHERE id = ?",
            (_iso_utc(now), task_id),
        )
        # Keep the steps with the idea.
        conn.execute(
            "UPDATE task_steps SET owner_kind = 'aion', owner_uid = ? "
            "WHERE owner_kind = 'task' AND owner_uid = ?",
            (uid, row["uid"]),
        )
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    idea = conn.execute("SELECT * FROM aion WHERE id = ?", (idea_id,)).fetchone()
    return _task_json(conn, task), _idea_json(idea, steps_for(conn, "aion", uid))


def add_idea(
    conn: sqlite3.Connection, *, text: str, why: str | None, now: datetime, note: str | None = None
) -> dict:
    uid = str(uuid.uuid4())
    with conn:
        conn.execute(
            "INSERT INTO aion (uid, text, why, note, status, created_at) "
            "VALUES (?, ?, ?, ?, 'open', ?)",
            (uid, text, why, note, _iso_utc(now)),
        )
    row = conn.execute("SELECT * FROM aion WHERE uid = ?", (uid,)).fetchone()
    return _idea_json(row)


def open_ideas(conn: sqlite3.Connection) -> list[dict]:
    """Open ideas, oldest first."""
    rows = conn.execute(
        "SELECT * FROM aion WHERE status = 'open' ORDER BY created_at, id"
    ).fetchall()
    return [_idea_json(row, steps_for(conn, "aion", row["uid"])) for row in rows]


def pull_idea(
    conn: sqlite3.Connection, *, idea_id: int, now: datetime, tz: tzinfo, open_hour: int
) -> tuple[dict, dict]:
    idea = get_open_idea(conn, idea_id)
    day = days.trident_day(now, tz, open_hour)
    if day_open_count(conn, day) >= MAX_TASKS_PER_DAY:
        raise CliError(PLAN_FULL, code=1)
    uid = str(uuid.uuid4())
    with conn:
        cursor = conn.execute(
            "INSERT INTO tasks "
            "(uid, text, status, created_at, created_day, task_date, note, aion_id) "
            "VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)",
            (
                uid,
                idea["text"],
                _iso_utc(now),
                day.isoformat(),
                day.isoformat(),
                idea["note"],
                idea_id,
            ),
        )
        task_id = cursor.lastrowid
        conn.execute(
            "UPDATE aion SET status = 'pulled', closed_at = ?, task_id = ? WHERE id = ?",
            (_iso_utc(now), task_id, idea_id),
        )
        conn.execute(
            "UPDATE task_steps SET owner_kind = 'task', owner_uid = ? "
            "WHERE owner_kind = 'aion' AND owner_uid = ?",
            (uid, idea["uid"]),
        )
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    changed = conn.execute("SELECT * FROM aion WHERE id = ?", (idea_id,)).fetchone()
    return _task_json(conn, task), _idea_json(changed, steps_for(conn, "aion", idea["uid"]))


def drop_idea(conn: sqlite3.Connection, *, idea_id: int, now: datetime) -> dict:
    idea = get_open_idea(conn, idea_id)
    with conn:
        conn.execute(
            "UPDATE aion SET status = 'dropped', closed_at = ? WHERE id = ?",
            (_iso_utc(now), idea_id),
        )
    row = conn.execute("SELECT * FROM aion WHERE id = ?", (idea_id,)).fetchone()
    return _idea_json(row, steps_for(conn, "aion", idea["uid"]))


def all_tasks(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return [_task_json(conn, row) for row in rows]


def all_ideas(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM aion ORDER BY id").fetchall()
    return [_idea_json(row, steps_for(conn, "aion", row["uid"])) for row in rows]

"""``trident task`` — the plan: dates, fields, steps, and moving tasks.

The plan never calls a task overdue, late or failed. A reminder is stored
metadata only; the CLI never speaks first.
"""

from __future__ import annotations

from trident_cli import clock, days, output, parser, plan, storage
from trident_cli.errors import EXIT_USAGE, CliError


def _label(task: dict) -> str:
    return f"#{task['id']}"


def _markers(task: dict) -> str:
    parts = []
    if task.get("is_frog"):
        parts.append("🐸")
    if task.get("remind_at"):
        parts.append(f"⏰ {task['remind_at']}")
    strategy = task.get("strategy")
    if strategy:
        parts.append(f"{strategy['kind']} #{strategy['id']}")
    steps = task.get("steps") or []
    if steps:
        done = sum(1 for step in steps if step["is_done"])
        parts.append(f"{done} of {len(steps)} steps")
    return " · ".join(parts)


def _entry_summary(entry: dict | None) -> str:
    if not entry:
        return ""
    parts = []
    for name, key in (("STR", "str"), ("AGI", "agi"), ("INT", "int")):
        value = entry["output"][key]
        if value:
            parts.append(f"{name} +{value}")
    if entry["cost"]:
        parts.append(f"🟡 {entry['cost']}")
    return " · ".join(parts)


def _rows(tasks: list[dict]) -> list[str]:
    rendered = []
    for task in tasks:
        prefix = f"  {_label(task):<5}{task['text']}"
        suffix = _markers(task)
        rendered.append((prefix, suffix))
    width = max((len(prefix) for prefix, suffix in rendered if suffix), default=0)
    return [prefix.ljust(width) + "  " + suffix if suffix else prefix for prefix, suffix in rendered]


def _done_rows(tasks: list[dict]) -> list[str]:
    rows = []
    for task in tasks:
        if task["status"] == "refused":
            prefix, suffix = f"  {_label(task):<5}let go · {task['text']}", ""
        else:
            prefix, suffix = f"  {_label(task):<5}{task['text']}", _entry_summary(task["entry"])
        rows.append((prefix, suffix))
    width = max((len(prefix) for prefix, suffix in rows if suffix), default=0)
    return [prefix.ljust(width) + "  " + suffix if suffix else prefix for prefix, suffix in rows]


def _render_list(data: dict) -> str:
    groups = [
        ("Plan", data["plan"]),
        ("From earlier", data["from_earlier"]),
        ("Underline", data["underline"]),
        ("Later", data["later"]),
    ]
    lines: list[str] = []
    for title, tasks in groups:
        if not tasks:
            continue
        if lines:
            lines.append("")
        lines.append(title)
        lines.extend(_rows(tasks))
    if data["done_today"]:
        if lines:
            lines.append("")
        lines.append("Done today")
        lines.extend(_done_rows(data["done_today"]))
    return "\n".join(lines) if lines else "The plan is clear."


def _plain(data: dict) -> str:
    tasks = data["plan"] + data["from_earlier"] + data["underline"] + data["later"]
    return "\n".join(f"{task['id']}\t{task['text']}" for task in tasks)


def _render_show(task: dict) -> str:
    lines = [f"{_label(task)}  {task['text']}"]
    if task["task_date"]:
        lines.append(f"    date       {task['task_date']}")
    if task["below_line"]:
        lines.append("    surface    Underline")
    if task["note"]:
        lines.append(f"    note       {task['note']}")
    if task["remind_at"]:
        lines.append(f"    reminder   {task['remind_at']}")
    if task["is_frog"]:
        lines.append("    frog       yes")
    strategy = task["strategy"]
    if strategy:
        title = f"  {strategy['title']}" if strategy["title"] else ""
        lines.append(f"    strategy   {strategy['kind']} #{strategy['id']}{title}")
    steps = task["steps"]
    if steps:
        done = sum(1 for step in steps if step["is_done"])
        lines.append(f"    steps      {done} of {len(steps)}")
        for step in steps:
            mark = "x" if step["is_done"] else ("-" if step["is_skipped"] else " ")
            lines.append(f"      [{mark}] {step['order']}. {step['text']}")
    if task["status"] != "pending":
        if task["status"] == "consumed":
            lines.append("    status     became a step of another task")
        else:
            lines.append(f"    status     {'done' if task['status'] == 'done' else 'let go'}")
    return "\n".join(lines)


def _strategy_from_args(args) -> tuple[str | None, int | None]:
    kind = getattr(args, "epic", None)
    if kind is not None:
        return "epic", plan.parse_strategy_id(kind)
    kind = getattr(args, "sprint", None)
    if kind is not None:
        return "sprint", plan.parse_strategy_id(kind)
    return None, None


def _add(args) -> int:
    words = list(getattr(args, "words", []))
    if not words:
        raise CliError("nothing to add", code=EXIT_USAGE)
    try:
        text = parser.validate_text(" ".join(words))
        note = parser.validate_note(args.note) if getattr(args, "note", None) is not None else None
    except parser.ParseError as exc:
        raise CliError(str(exc), code=EXIT_USAGE) from exc

    below_line = bool(getattr(args, "underline", False))
    is_frog = bool(getattr(args, "frog", False))
    if below_line and is_frog:
        raise CliError("a frog is a dated task, not an Underline task", code=EXIT_USAGE)
    if below_line and getattr(args, "date", None):
        raise CliError("--underline takes no --date", code=EXIT_USAGE)

    task_date = plan.parse_date(args.date) if getattr(args, "date", None) else None
    remind_at = plan.parse_remind(args.remind) if getattr(args, "remind", None) else None
    strategy_kind, strategy_id = _strategy_from_args(args)

    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        task = plan.add_task(
            conn,
            text=text,
            now=moment,
            tz=tz,
            open_hour=open_hour,
            task_date=task_date,
            note=note,
            remind_at=remind_at,
            is_frog=is_frog,
            below_line=below_line,
            strategy_kind=strategy_kind,
            strategy_id=strategy_id,
        )
    finally:
        conn.close()

    output.emit(task, lambda item: f"Added #{item['id']} · {item['text']}")
    return 0


def _edit(args) -> int:
    task_id = plan.parse_id(args.id)
    changes: dict = {}
    if getattr(args, "text", None) is not None:
        try:
            changes["text"] = parser.validate_text(args.text)
        except parser.ParseError as exc:
            raise CliError(str(exc), code=EXIT_USAGE) from exc
    if getattr(args, "note", None) is not None:
        try:
            changes["note"] = parser.validate_note(args.note)
        except parser.ParseError as exc:
            raise CliError(str(exc), code=EXIT_USAGE) from exc
    if getattr(args, "remind", None) is not None:
        changes["remind_at"] = plan.parse_remind(args.remind)
    if getattr(args, "no_remind", False):
        changes["remind_at"] = ""
    if getattr(args, "date", None) is not None:
        changes["task_date"] = plan.parse_date(args.date)
    if getattr(args, "frog", False):
        changes["is_frog"] = True
    if getattr(args, "no_frog", False):
        changes["is_frog"] = False
    if getattr(args, "underline", False):
        changes["below_line"] = True
    if getattr(args, "no_underline", False):
        changes["below_line"] = False
    if getattr(args, "no_strategy", False):
        changes["clear_strategy"] = True
    if getattr(args, "epic", None) is not None or getattr(args, "sprint", None) is not None:
        kind, ident = _strategy_from_args(args)
        changes["strategy_kind"] = kind
        changes["strategy_id"] = ident
    if not changes:
        raise CliError("nothing to change", code=EXIT_USAGE)

    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        today = days.trident_day(moment, tz, open_hour)
        if changes.get("below_line") is False:
            changes.setdefault("default_day", today)
        task = plan.edit_task(conn, task_id=task_id, now=moment, **changes)
    finally:
        conn.close()

    output.emit(task, lambda item: f"Updated #{item['id']} · {item['text']}")
    return 0


def _move(args) -> int:
    task_id = plan.parse_id(args.id)
    target = plan.parse_date(args.date)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        task = plan.move_task(conn, task_id=task_id, target_date=target, now=moment)
    finally:
        conn.close()

    output.emit(task, lambda item: f"Moved #{item['id']} to {item['task_date']}.")
    return 0


def _later(args) -> int:
    task_id = plan.parse_id(args.id)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        task, idea = plan.move_to_aion(conn, task_id=task_id, now=moment)
    finally:
        conn.close()

    payload = {"task": task, "idea": idea}
    output.emit(
        payload,
        lambda data: f"Moved #{data['task']['id']} to Aion as #{data['idea']['id']}.",
    )
    return 0


def _subtask(args) -> int:
    child_id = plan.parse_id(args.id)
    parent_id = plan.parse_id(args.parent)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        child, parent, step = plan.subtask(
            conn, child_id=child_id, parent_id=parent_id, now=moment
        )
    finally:
        conn.close()

    payload = {"task": child, "parent": parent, "step": step}
    output.emit(
        payload,
        lambda data: f"Made #{data['task']['id']} a step of #{data['parent']['id']}.",
    )
    return 0


def _show(args) -> int:
    task_id = plan.parse_id(args.id)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        task = plan.get_task(conn, task_id)
        payload = plan._task_json(conn, task)
    finally:
        conn.close()

    output.emit(payload, _render_show)
    return 0


def _step(args) -> int:
    action = getattr(args, "step_command", None)
    if action not in ("add", "remove", "done", "skip", "resume"):
        raise CliError("choose a step action: add, remove, done, skip or resume", code=EXIT_USAGE)
    task_id = plan.parse_id(args.step_task)
    words = list(getattr(args, "words", []))
    if action == "add":
        if not words:
            raise CliError("nothing to add", code=EXIT_USAGE)
        try:
            text = parser.validate_text(" ".join(words))
        except parser.ParseError as exc:
            raise CliError(str(exc), code=EXIT_USAGE) from exc
        moment = clock.now()
        conn, _tz, _open_hour = storage.open_journal(moment)
        try:
            task = plan.add_step(conn, task_id=task_id, text=text, now=moment)
        finally:
            conn.close()
        order = len(task["steps"])
        output.emit(task, lambda item: f"Added step {order} to #{item['id']}.")
        return 0

    if action == "remove":
        order = plan.parse_id(args.order)
        moment = clock.now()
        conn, _tz, _open_hour = storage.open_journal(moment)
        try:
            task = plan.remove_step(conn, task_id=task_id, order=order, now=moment)
        finally:
            conn.close()
        output.emit(task, lambda item: f"Removed step {order} from #{item['id']}.")
        return 0

    if action not in ("done", "skip", "resume"):
        raise CliError("nothing to do", code=EXIT_USAGE)
    order = plan.parse_id(args.order)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        plan_action = "complete" if action == "done" else action
        task = plan.set_step(conn, task_id=task_id, order=order, action=plan_action, now=moment)
    finally:
        conn.close()

    verb = {"done": "done", "skip": "skipped", "resume": "resumed"}[action]
    output.emit(task, lambda item: f"Step {order} {verb}.")
    return 0


def _list(args) -> int:
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        today = days.trident_day(moment, tz, open_hour)
        current = plan.parse_date(args.date) if getattr(args, "date", None) else today
        groups = plan.open_tasks(conn, current)
        done = plan.done_today(conn, current, tz, open_hour)
    finally:
        conn.close()

    payload = {**groups, "done_today": done}
    plain = bool(getattr(args, "plain", False))
    output.emit(payload, _plain if plain else _render_list)
    return 0


def run(args) -> int:
    command = getattr(args, "task_command", None)
    if command == "add":
        return _add(args)
    if command == "edit":
        return _edit(args)
    if command == "move":
        return _move(args)
    if command == "later":
        return _later(args)
    if command == "subtask":
        return _subtask(args)
    if command == "show":
        return _show(args)
    if command == "step":
        return _step(args)
    return _list(args)

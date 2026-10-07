"""``trident done`` — complete a task and write its journal entry."""

from __future__ import annotations

from trident_cli import clock, output, parser, plan, storage
from trident_cli.commands import log as log_cmd
from trident_cli.errors import EXIT_USAGE, CliError


def _render(task: dict) -> str:
    parts = [f"Done #{task['id']}"]
    entry = task.get("entry")
    if entry:
        for name, key in (("STR", "str"), ("AGI", "agi"), ("INT", "int")):
            value = entry["output"][key]
            if value:
                parts.append(f"{name} +{value}")
        if entry["cost"]:
            parts.append(f"🟡 {entry['cost']}")
    if len(parts) == 1:
        return f"{parts[0]}."
    return " · ".join(parts)


def run(args) -> int:
    task_id = plan.parse_id(args.id)
    silent = bool(getattr(args, "silent", False))
    interactive = bool(getattr(args, "interactive", False))
    words = list(getattr(args, "words", []))

    if silent and (words or interactive):
        raise CliError("--silent takes no attributes", code=EXIT_USAGE)
    if interactive and words:
        raise CliError("use either inline attributes or -i", code=EXIT_USAGE)

    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        plan.get_open_task(conn, task_id)  # fail before any prompt

        points = {"str_points": 0, "agi_points": 0, "int_points": 0, "will_points": 0}
        if interactive:
            points = log_cmd._ask()
        elif words:
            try:
                parsed = parser.parse_pairs(" ".join(words))
            except parser.ParseError as exc:
                raise CliError(str(exc), code=EXIT_USAGE) from exc
            points = {
                "str_points": parsed.str_points,
                "agi_points": parsed.agi_points,
                "int_points": parsed.int_points,
                "will_points": parsed.will_points,
            }

        task = plan.complete_task(
            conn,
            task_id=task_id,
            now=moment,
            tz=tz,
            open_hour=open_hour,
            silent=silent,
            **points,
        )
    finally:
        conn.close()

    output.emit(task, _render)
    return 0

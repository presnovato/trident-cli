"""``trident aion`` — the backlog of ideas."""

from __future__ import annotations

from trident_cli import clock, output, parser, plan, storage
from trident_cli.errors import EXIT_USAGE, CliError


def _render_list(data: dict) -> str:
    ideas = data["ideas"]
    if not ideas:
        return "Aion is empty."
    lines = []
    for idea in ideas:
        lines.append(f"#{idea['id']}  {idea['text']}")
        if idea["why"]:
            lines.append(f"  why: {idea['why']}")
        if idea["note"]:
            lines.append(f"  note: {idea['note']}")
    return "\n".join(lines)


def _plain(data: dict) -> str:
    return "\n".join(f"{idea['id']}\t{idea['text']}" for idea in data["ideas"])


def _list(args) -> int:
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        ideas = plan.open_ideas(conn)
    finally:
        conn.close()

    payload = {"ideas": ideas}
    plain = bool(getattr(args, "plain", False))
    output.emit(payload, _plain if plain else _render_list)
    return 0


def _add(args) -> int:
    words = list(getattr(args, "words", []))
    if not words:
        raise CliError("nothing to add", code=EXIT_USAGE)
    why = getattr(args, "why", None)
    note_arg = getattr(args, "note", None)
    try:
        text = parser.validate_text(" ".join(words))
        why_value = parser.validate_why(why) if why is not None else None
        note_value = parser.validate_note(note_arg) if note_arg is not None else None
    except parser.ParseError as exc:
        raise CliError(str(exc), code=EXIT_USAGE) from exc

    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        idea = plan.add_idea(
            conn, text=text, why=why_value, note=note_value, now=moment
        )
    finally:
        conn.close()

    output.emit(idea, lambda item: f"Added #{item['id']} to Aion.")
    return 0


def _pull(args) -> int:
    idea_id = plan.parse_id(args.id)
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        task, idea = plan.pull_idea(
            conn, idea_id=idea_id, now=moment, tz=tz, open_hour=open_hour
        )
    finally:
        conn.close()

    payload = {"task": task, "idea": idea}
    output.emit(
        payload,
        lambda data: f"Pulled #{data['idea']['id']} into the plan as #{data['task']['id']}.",
    )
    return 0


def _drop(args) -> int:
    idea_id = plan.parse_id(args.id)
    moment = clock.now()
    conn, _tz, _open_hour = storage.open_journal(moment)
    try:
        idea = plan.drop_idea(conn, idea_id=idea_id, now=moment)
    finally:
        conn.close()

    output.emit(idea, lambda item: f"Dropped #{item['id']}.")
    return 0


def run(args) -> int:
    command = getattr(args, "aion_command", None)
    if command == "add":
        return _add(args)
    if command == "pull":
        return _pull(args)
    if command == "drop":
        return _drop(args)
    return _list(args)

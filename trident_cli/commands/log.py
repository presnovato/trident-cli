"""``trident log`` — write down what happened."""

from __future__ import annotations

import sys

from trident_cli import clock, journal, output, parser, storage
from trident_cli.errors import EXIT_USAGE, CliError

# (keyword for ParsedEntry, prompt shown on stderr)
_PROMPTS: list[tuple[str, str]] = [
    ("str_points", "Output — STR (body) 0–3 [0]:"),
    ("agi_points", "Output — AGI (people) 0–3 [0]:"),
    ("int_points", "Output — INT (mind) 0–3 [0]:"),
    ("will_points", "What did it cost? WILL 0–3 [0]:"),
]

_ALLOWED = {"0", "1", "2", "3"}


def _parse(raw: str) -> parser.ParsedEntry:
    try:
        return parser.parse_entry(raw)
    except parser.ParseError as exc:
        raise CliError(str(exc), code=EXIT_USAGE) from exc


def _read_stdin() -> str:
    # PowerShell may prefix piped text with a byte-order mark.
    return sys.stdin.read().lstrip("﻿")


def _read_raw(words: list[str]) -> str:
    if words == ["-"]:
        return _read_stdin()
    if not words:
        if sys.stdin.isatty():
            raise CliError("nothing to log", code=EXIT_USAGE)
        return _read_stdin()
    return " ".join(words)


def _ask() -> dict[str, int]:
    """Ask the four questions on stderr, reading answers from the terminal."""
    if not sys.stdin.isatty():
        raise CliError("interactive mode needs a terminal", code=EXIT_USAGE)

    answers: dict[str, int] = {}
    for key, question in _PROMPTS:
        while True:
            output.prompt(question)
            try:
                answer = input().strip()
            except EOFError as exc:
                raise CliError("nothing to log", code=EXIT_USAGE) from exc
            if answer == "":
                answers[key] = 0
                break
            if answer in _ALLOWED:
                answers[key] = int(answer)
                break
    return answers


def _store(parsed: parser.ParsedEntry) -> dict:
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        return journal.add_entry(
            conn,
            kind="done",
            text=parsed.text,
            occurred_at=moment,
            tz=tz,
            open_hour=open_hour,
            str_points=parsed.str_points,
            agi_points=parsed.agi_points,
            int_points=parsed.int_points,
            will_points=parsed.will_points,
        )
    finally:
        conn.close()


def _render(entry: dict) -> str:
    parts = ["Logged"]
    for name, key in (("STR", "str"), ("AGI", "agi"), ("INT", "int")):
        value = entry["output"][key]
        if value:
            parts.append(f"{name} +{value}")
    if entry["cost"]:
        parts.append(f"🟡 {entry['cost']}")
    if len(parts) == 1:
        return "Logged."
    return " · ".join(parts)


def run(args) -> int:
    interactive = bool(getattr(args, "interactive", False))
    words = list(getattr(args, "words", []))

    if interactive:
        if not words:
            raise CliError("nothing to log", code=EXIT_USAGE)
        parsed = _parse(" ".join(words))
        if parsed.has_attributes:
            raise CliError("use either inline attributes or -i", code=EXIT_USAGE)
        answers = _ask()
        parsed = parser.ParsedEntry(text=parsed.text, **answers)
    else:
        parsed = _parse(_read_raw(words))

    entry = _store(parsed)
    output.emit(entry, _render)
    return 0

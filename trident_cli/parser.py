"""Parsing a hand-written entry into text and optional attribute points.

Pure: no I/O, no clock, no settings, so it is unit-tested on its own.

An entry is text plus optional pairs. A pair is ``+N ATTR`` or ``ATTR +N``
with ``N`` in 1–3. Pairs are recognised only in two places:

* an **attribute line** — a line made only of pairs;
* a **trailing run** of pairs at the end of a text line.

A pair standing alone in the middle of a sentence is text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TEXT = 4000
MAX_WHY = 1000
MAX_NOTE = 1000

# alias (lower-cased) -> canonical attribute key
_ATTRS: dict[str, str] = {
    "str": "str",
    "agi": "agi",
    "int": "int",
    "will": "will",
    "тело": "str",
    "люди": "agi",
    "разум": "int",
    "воля": "will",
}

_POINTS_RE = re.compile(r"[+-]\d+")
_TOKEN_RE = re.compile(r"\S+")


class ParseError(ValueError):
    """The entry cannot be parsed."""


@dataclass(frozen=True)
class ParsedEntry:
    """The result of parsing one entry."""

    text: str
    str_points: int = 0
    agi_points: int = 0
    int_points: int = 0
    will_points: int = 0
    has_attributes: bool = False


def _is_attr(token: str) -> bool:
    return token.lower() in _ATTRS


def _is_points(token: str) -> bool:
    return _POINTS_RE.fullmatch(token) is not None


def _points(token: str) -> int:
    value = int(token)
    if not 1 <= value <= 3:
        raise ParseError("points must be 1–3")
    return value


def _match_pair(first: str, second: str) -> tuple[str, int] | None:
    """Return ``(attribute, points)`` when two tokens form a pair, else None."""
    if _is_points(first) and _is_attr(second):
        return _ATTRS[second.lower()], _points(first)
    if _is_attr(first) and _is_points(second):
        return _ATTRS[first.lower()], _points(second)
    return None


def _attribute_line_pairs(line: str) -> list[tuple[str, int]] | None:
    """Parse a line that should consist only of pairs, or return None."""
    tokens = line.split()
    if not tokens:
        return None
    pairs: list[tuple[str, int]] = []
    index = 0
    while index < len(tokens):
        if index + 1 >= len(tokens):
            return None
        pair = _match_pair(tokens[index], tokens[index + 1])
        if pair is None:
            return None
        pairs.append(pair)
        index += 2
    return pairs


def _take_trailing_pairs(line: str) -> tuple[str, list[tuple[str, int]]]:
    """Split off the unbroken run of pairs at the end of ``line``.

    Returns ``(remaining_text, pairs)``. Internal spacing before the run is
    preserved; only the pairs themselves are removed.
    """
    matches = list(_TOKEN_RE.finditer(line))
    tokens = [match.group() for match in matches]
    pairs: list[tuple[str, int]] = []
    index = len(tokens)
    start = len(line)
    while index >= 2:
        pair = _match_pair(tokens[index - 2], tokens[index - 1])
        if pair is None:
            break
        pairs.append(pair)
        start = matches[index - 2].start()
        index -= 2
    pairs.reverse()
    return line[:start].rstrip(), pairs


def parse_entry(raw: str) -> ParsedEntry:
    """Parse ``raw`` into a :class:`ParsedEntry` or raise :class:`ParseError`."""
    lines = [line.strip() for line in raw.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()

    first_attr: int | None = None
    for index, line in enumerate(lines):
        if line and _attribute_line_pairs(line) is not None:
            first_attr = index
            break

    text_lines = lines if first_attr is None else lines[:first_attr]
    pairs: list[tuple[str, int]] = []

    if text_lines:
        remaining, trailing = _take_trailing_pairs(text_lines[-1])
        pairs.extend(trailing)
        text_lines = text_lines[:-1] + [remaining]

    if first_attr is not None:
        for line in lines[first_attr:]:
            line_pairs = _attribute_line_pairs(line)
            if line_pairs is None:
                raise ParseError("text after attributes")
            pairs.extend(line_pairs)

    values = {"str": 0, "agi": 0, "int": 0, "will": 0}
    for attribute, amount in pairs:
        if values[attribute]:
            raise ParseError("each attribute may appear at most once")
        values[attribute] = amount

    text = "\n".join(text_lines).strip()
    if not text:
        raise ParseError("write what happened")
    if len(text) > MAX_TEXT:
        raise ParseError(f"entry is too long (max {MAX_TEXT} characters)")

    return ParsedEntry(
        text=text,
        str_points=values["str"],
        agi_points=values["agi"],
        int_points=values["int"],
        will_points=values["will"],
        has_attributes=bool(pairs),
    )


def validate_text(raw: str) -> str:
    """Text-only validation for a task or an idea: non-empty, at most ``MAX_TEXT``."""
    text = raw.strip()
    if not text:
        raise ParseError("write what happened")
    if len(text) > MAX_TEXT:
        raise ParseError(f"entry is too long (max {MAX_TEXT} characters)")
    return text


def validate_why(raw: str) -> str:
    """An idea's optional "why", at most ``MAX_WHY`` characters."""
    why = raw.strip()
    if len(why) > MAX_WHY:
        raise ParseError(f"why is too long (max {MAX_WHY} characters)")
    return why


def validate_note(raw: str) -> str:
    """A task or idea note, at most ``MAX_NOTE`` characters. Empty clears it."""
    note = raw.strip()
    if len(note) > MAX_NOTE:
        raise ParseError(f"note is too long (max {MAX_NOTE} characters)")
    return note


def parse_pairs(raw: str) -> ParsedEntry:
    """Parse a trailing run of attribute pairs with no text of its own.

    A sentinel word is prepended so the ordinary pair rules apply; if anything
    but pairs survives, the caller passed text to a command that takes none.
    """
    parsed = parse_entry("x " + raw.strip())
    if parsed.text != "x":
        raise ParseError("only attributes are allowed here")
    return parsed

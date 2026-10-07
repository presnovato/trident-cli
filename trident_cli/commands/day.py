"""``trident day`` — show one Trident day, neutrally."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from trident_cli import clock, days, journal, output, storage
from trident_cli.errors import EXIT_USAGE, CliError

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _resolve_day(args, current: date) -> date:
    raw_date = getattr(args, "date", None)
    if raw_date:
        try:
            target = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise CliError("--date must look like YYYY-MM-DD", code=EXIT_USAGE) from exc
    elif getattr(args, "yesterday", False):
        target = current - timedelta(days=1)
    else:
        target = current

    if target > current:
        raise CliError("cannot show a future day", code=EXIT_USAGE)
    return target


def _totals(entries: list[dict]) -> tuple[dict, int]:
    output_points = {"str": 0, "agi": 0, "int": 0}
    cost = 0
    for entry in entries:
        if entry["kind"] != "done":
            continue
        output_points["str"] += entry["output"]["str"]
        output_points["agi"] += entry["output"]["agi"]
        output_points["int"] += entry["output"]["int"]
        cost += entry["cost"]
    return output_points, cost


def _time_local(occurred_at: str, tz) -> str:
    return datetime.fromisoformat(occurred_at).astimezone(tz).strftime("%H:%M")


def _output_summary(entry: dict) -> str:
    parts = []
    for name, key in (("STR", "str"), ("AGI", "agi"), ("INT", "int")):
        value = entry["output"][key]
        if value:
            parts.append(f"{name} +{value}")
    if entry["cost"]:
        parts.append(f"🟡 {entry['cost']}")
    return " · ".join(parts)


def day_header(target: date) -> str:
    """``Thursday, 2 October`` — shared with ``history``."""
    return f"{_WEEKDAYS[target.weekday()]}, {target.day} {_MONTHS[target.month - 1]}"


def day_payload(conn, target: date, tz, open_hour: int) -> dict:
    """The JSON object shared by ``trident day`` and ``trident history``."""
    entries = journal.entries_for_day(conn, target)
    status = journal.day_status(conn, target)
    window_start, window_end = days.day_window(target, tz, open_hour)
    output_points, cost = _totals(entries)

    rest_reason = None
    if status == "rest":
        rest_reason = next(
            (entry["stop_reason"] for entry in entries if entry["kind"] == "stop"), None
        )

    return {
        "trident_day": target.isoformat(),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "status": status,
        "rest_reason": rest_reason,
        "entries": entries,
        "output": output_points,
        "cost": cost,
    }


def entry_lines(entries: list[dict], tz) -> list[str]:
    """The day's entries, one aligned line each; shared with ``history``."""
    rendered = []
    for entry in entries:
        if entry["kind"] == "stop":
            display, summary = "🌿 rest day", ""
        elif entry["kind"] == "refuse":
            display, summary = f"let go · {entry['text']}", ""
        else:
            display, summary = entry["text"], _output_summary(entry)
        prefix = f"{_time_local(entry['occurred_at'], tz)}  {display}"
        rendered.append((prefix, summary))
    width = max((len(prefix) for prefix, summary in rendered if summary), default=0)
    return [prefix.ljust(width) + "  " + summary if summary else prefix for prefix, summary in rendered]


def _render(payload: dict, tz, open_hour: int) -> str:
    target = date.fromisoformat(payload["trident_day"])
    header = f"{day_header(target)} · {open_hour:02d}:00 → {open_hour:02d}:00"
    entries = payload["entries"]
    lines = [header, ""]

    if payload["status"] == "rest":
        reason = payload["rest_reason"]
        banner = "🌿 Rest day"
        if reason:
            banner += f" · {journal.REASON_LABELS.get(reason, reason)}"
        lines.extend([banner, ""])

    has_done = any(entry["kind"] == "done" for entry in entries)
    listed = [entry for entry in entries if entry["kind"] != "stop" or has_done]
    if listed:
        lines.extend(entry_lines(listed, tz))
        lines.append("")

    if not entries:
        lines.append("No entries for this day.")
    else:
        points = payload["output"]
        lines.append(f"Output   STR {points['str']} · AGI {points['agi']} · INT {points['int']}")
        lines.append(f"Cost     🟡 {payload['cost']}")

    return "\n".join(lines)


def run(args) -> int:
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        current = days.trident_day(moment, tz, open_hour)
        target = _resolve_day(args, current)
        payload = day_payload(conn, target, tz, open_hour)
    finally:
        conn.close()

    output.emit(payload, lambda data: _render(data, tz, open_hour))
    return 0

"""``trident history`` — past days that have entries, newest first."""

from __future__ import annotations

import re
from datetime import date, timedelta

from trident_cli import clock, days, journal, output, seasons, storage
from trident_cli.commands import day as day_cmd
from trident_cli.errors import EXIT_USAGE, CliError

_SINCE_RE = re.compile(r"(\d+)d")


def _parse_until(raw: str | None, today: date) -> date:
    if raw is None:
        return today
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise CliError("--until must look like YYYY-MM-DD", code=EXIT_USAGE) from exc


def _parse_since(raw: str | None, until: date) -> date | None:
    if raw is None:
        return until - timedelta(days=6)
    if raw == "all":
        return None
    match = _SINCE_RE.fullmatch(raw)
    if match is not None:
        count = int(match.group(1))
        if count < 1:
            raise CliError("--since must be Nd with N at least 1", code=EXIT_USAGE)
        return until - timedelta(days=count - 1)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise CliError("--since must be Nd, an ISO date, or all", code=EXIT_USAGE) from exc


def _render_block(payload: dict, tz) -> str:
    target = date.fromisoformat(payload["trident_day"])
    lines = [day_cmd.day_header(target)]
    entries = payload["entries"]
    has_done = any(entry["kind"] == "done" for entry in entries)
    listed = [entry for entry in entries if entry["kind"] != "stop" or has_done]

    if payload["status"] == "rest":
        banner = "🌿 Rest day"
        if payload["rest_reason"]:
            banner += f" · {journal.REASON_LABELS.get(payload['rest_reason'], payload['rest_reason'])}"
        lines.append(banner)
        if not listed:
            return "\n".join(lines)

    lines.extend(day_cmd.entry_lines(listed, tz))
    points = payload["output"]
    lines.append(
        f"Output STR {points['str']} · AGI {points['agi']} · INT {points['int']} · 🟡 {payload['cost']}"
    )
    return "\n".join(lines)


def run(args) -> int:
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        today = days.trident_day(moment, tz, open_hour)
        until = _parse_until(getattr(args, "until", None), today)
        since = _parse_since(getattr(args, "since", None), until)
        if since is not None and since > until:
            raise CliError("--since is later than --until", code=EXIT_USAGE)
        days_with_entries = seasons.days_with_entries(conn, since, until)
        payloads = [day_cmd.day_payload(conn, day, tz, open_hour) for day in days_with_entries]
    finally:
        conn.close()

    payload = {
        "since": since.isoformat() if since is not None else None,
        "until": until.isoformat(),
        "days": payloads,
    }

    def render(data: dict) -> str:
        if not data["days"]:
            return "No entries in this range."
        return "\n\n".join(_render_block(day, tz) for day in data["days"])

    output.emit(payload, render)
    return 0

"""``trident season`` — the current chapter, one closed season, or a list."""

from __future__ import annotations

from datetime import date

from trident_cli import clock, counting, days, journal, output, seasons, storage
from trident_cli.errors import EXIT_USAGE, CliError

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _long(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]}"


def _short(day: date) -> str:
    return f"{day.day} {_MONTHS_SHORT[day.month - 1]}"


def _cells_out(cells: list[str]) -> str:
    groups = ["".join(cells[index:index + 7]) for index in range(0, 28, 7)]
    return " ".join(groups)


def _strip_lines(cells: list[str]) -> list[str]:
    return [f"Days  {_cells_out(cells)}", "      ● entries   ~ rest day"]


def _current_payload(conn, summary: dict, current: date) -> dict:
    number = summary["number"]
    start = date.fromisoformat(summary["start_day"])
    return {
        "number": number,
        "start_day": summary["start_day"],
        "end_day": summary["end_day"],
        "closed": False,
        "day_number": counting.season_day_number(start, current),
        "output": summary["output"],
        "cost": summary["cost"],
        "today": journal.day_points(conn, current),
        "base": seasons.base_totals(conn),
        "strip": seasons.day_strip(conn, number),
    }


def _render_current(payload: dict, open_hour: int) -> str:
    today = payload["today"]
    base = payload["base"]
    lines = [
        f"Season {payload['number']} · day {payload['day_number']} of 28 · "
        f"{_long(date.fromisoformat(payload['start_day']))} → {_long(date.fromisoformat(payload['end_day']))}",
        "",
        f"This season   STR {payload['output']['str']} · AGI {payload['output']['agi']} · INT {payload['output']['int']}",
        f"Cost          🟡 {payload['cost']}",
        f"Today so far  STR {today['output']['str']} · AGI {today['output']['agi']} · "
        f"INT {today['output']['int']} · 🟡 {today['cost']}  "
        f"(closes into the season at {open_hour:02d}:00)",
        "",
        f"Life          STR {base['output']['str']} · AGI {base['output']['agi']} · INT {base['output']['int']}",
        f"Life cost     🟡 {base['cost']}",
        "",
        *_strip_lines(payload["strip"]),
    ]
    return "\n".join(lines)


def _render_closed(payload: dict) -> str:
    gain = payload["base_gain"]
    lines = [
        f"Season {payload['number']} · {_long(date.fromisoformat(payload['start_day']))} → "
        f"{_long(date.fromisoformat(payload['end_day']))} · closed",
        "",
        f"Season    STR {payload['output']['str']} · AGI {payload['output']['agi']} · INT {payload['output']['int']}",
        f"Cost      🟡 {payload['cost']}",
        f"To life   STR +{gain['output']['str']} · AGI +{gain['output']['agi']} · "
        f"INT +{gain['output']['int']} · 🟡 +{gain['cost']}",
        "",
        *_strip_lines(payload["strip"]),
    ]
    return "\n".join(lines)








def _list_payload(conn) -> dict:
    items = []
    for row in reversed(seasons.all_seasons(conn)):
        number = row["number"]
        item = {
            "number": number,
            "start_day": row["start_day"],
            "end_day": counting.season_end(date.fromisoformat(row["start_day"])).isoformat(),
            "closed": row["closed_at"] is not None,
            "output": None,
            "cost": None,
        }
        if item["closed"]:
            totals = seasons.season_totals(conn, number)
            item["output"] = totals["output"]
            item["cost"] = totals["cost"]
        items.append(item)
    return {"source": "local", "seasons": items}


def _render_list(payload: dict) -> str:
    lines = []
    for item in payload["seasons"]:
        start = date.fromisoformat(item["start_day"])
        end = date.fromisoformat(item["end_day"])
        head = f"Season {item['number']} · {_short(start)} → {_short(end)}"
        if not item["closed"]:
            lines.append(f"{head} · open")
        else:
            out = item["output"]
            lines.append(
                f"{head} · STR {out['str']} · AGI {out['agi']} · INT {out['int']} · 🟡 {item['cost']}"
            )
    return "\n".join(lines)


def run(args) -> int:
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        current = days.trident_day(moment, tz, open_hour)
        if getattr(args, "list", False):
            payload = _list_payload(conn)
            renderer = _render_list
        else:
            number = getattr(args, "number", None)
            if number is None:
                row = seasons.current_season(conn)
                if row is None:
                    raise CliError("no season yet", code=EXIT_USAGE)
                number = row["number"]

            summary = seasons.season_summary(conn, number)
            if summary is None:
                raise CliError(f"unknown season: {number}", code=EXIT_USAGE)
            if summary["closed"]:
                payload = {**summary, "strip": seasons.day_strip(conn, number)}
                renderer = _render_closed
            else:
                payload = _current_payload(conn, summary, current)
                renderer = lambda data: _render_current(data, open_hour)
    finally:
        conn.close()

    output.emit(payload, renderer)
    return 0

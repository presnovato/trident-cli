"""``trident export`` — the whole journal as JSON or CSV."""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date, timezone
from pathlib import Path

from trident_cli import clock, counting, journal, output, plan, seasons, settings, storage
from trident_cli.errors import EXIT_USAGE, CliError

_CSV_HEADER = ["uid", "kind", "trident_day", "occurred_at", "text", "str", "agi", "int", "will", "stop_reason"]


def _totals(row) -> dict:
    return {
        "output": {"str": row["str_total"], "agi": row["agi_total"], "int": row["int_total"]},
        "cost": row["will_total"],
    }


def _gains(row) -> dict:
    return {
        "output": {"str": row["str_gain"], "agi": row["agi_gain"], "int": row["int_gain"]},
        "cost": row["will_gain"],
    }


def _json_payload(entries, closed, season_rows, tz_value, open_hour, moment, tasks, ideas) -> dict:
    return {
        "format_version": 1,
        "exported_at": moment.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "settings": {"timezone": tz_value, "day_open_hour": open_hour},
        "entries": entries,
        "closed_days": [
            {
                "trident_day": row["trident_day"],
                "season": row["season_number"],
                "totals": _totals(row),
                "gains": _gains(row),
            }
            for row in closed
        ],
        "seasons": [
            {
                "number": row["number"],
                "start_day": row["start_day"],
                "end_day": counting.season_end(date.fromisoformat(row["start_day"])).isoformat(),
                "closed": row["closed_at"] is not None,
                "base_gain": None if row["closed_at"] is None else _gains(row),
            }
            for row in season_rows
        ],
        "tasks": tasks,
        "aion": ideas,
    }


def _csv_text(entries) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)
    for entry in entries:
        writer.writerow(
            [
                entry["uid"],
                entry["kind"],
                entry["trident_day"],
                entry["occurred_at"],
                entry["text"],
                entry["output"]["str"],
                entry["output"]["agi"],
                entry["output"]["int"],
                entry["cost"],
                entry["stop_reason"] or "",
            ]
        )
    return buffer.getvalue()


def run(args) -> int:
    moment = clock.now()
    conn, _tz, open_hour = storage.open_journal(moment)
    try:
        entries = journal.all_entries(conn)
        closed = seasons.closed_days(conn)
        season_rows = seasons.all_seasons(conn)
        tasks = plan.all_tasks(conn)
        ideas = plan.all_ideas(conn)
        tz_value, _source = settings.resolve(conn, "timezone")
    finally:
        conn.close()

    fmt = getattr(args, "format", "json") or "json"
    if fmt == "csv":
        blob = "\ufeff" + _csv_text(entries)
    else:
        payload = _json_payload(entries, closed, season_rows, tz_value, open_hour, moment, tasks, ideas)
        blob = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    path_arg = getattr(args, "output", None)
    if path_arg:
        path = Path(path_arg)
        if path.exists() and not getattr(args, "force", False):
            raise CliError(f"{path_arg} already exists — use --force to overwrite", code=EXIT_USAGE)
        path.write_bytes(blob.encode("utf-8"))
        output.error(f"Exported {len(entries)} entries to {path_arg}")
    else:
        sys.stdout.write(blob)
        sys.stdout.flush()
    return 0

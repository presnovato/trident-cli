"""``trident stop`` — mark a rest day."""

from __future__ import annotations

from trident_cli import clock, days, journal, output, storage


def _render(entry: dict) -> str:
    reason = entry["stop_reason"]
    if reason:
        return f"🌿 Rest day · {journal.REASON_LABELS.get(reason, reason)}"
    return "🌿 Rest day."


def run(args) -> int:
    reason = getattr(args, "reason", None)
    moment = clock.now()

    conn, tz, open_hour = storage.open_journal(moment)
    try:
        target = days.trident_day(moment, tz, open_hour)
        entry = journal.add_stop(
            conn, occurred_at=moment, tz=tz, open_hour=open_hour, reason=reason
        )
    finally:
        conn.close()

    if entry is None:
        output.emit(
            {"added": False, "trident_day": target.isoformat()},
            lambda _data: "Already a rest day.",
        )
        return 0

    output.emit(entry, _render)
    return 0

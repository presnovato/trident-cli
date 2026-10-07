"""``trident refuse`` — let a task go; a fact of the day, not a failure."""

from __future__ import annotations

from trident_cli import clock, output, plan, storage


def run(args) -> int:
    task_id = plan.parse_id(args.id)
    moment = clock.now()
    conn, tz, open_hour = storage.open_journal(moment)
    try:
        task = plan.refuse_task(
            conn, task_id=task_id, now=moment, tz=tz, open_hour=open_hour
        )
    finally:
        conn.close()

    output.emit(task, lambda item: f"Let go #{item['id']}.")
    return 0

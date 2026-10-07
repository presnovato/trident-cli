"""``trident config list|get|set|unset``."""

from __future__ import annotations

from trident_cli import output, settings, storage


def cmd_help(args) -> int:
    args.parser.print_help()
    return 0


def cmd_list(_args) -> int:
    conn = storage.connect()
    try:
        rows = settings.list_all(conn)
    finally:
        conn.close()

    def render(items) -> str:
        return "\n".join(f"{item['key']}: {item['value']} ({item['source']})" for item in items)

    output.emit(rows, render)
    return 0


def cmd_get(args) -> int:
    conn = storage.connect()
    try:
        value, source = settings.resolve(conn, args.key)
    finally:
        conn.close()

    output.emit({"key": args.key, "value": value, "source": source}, lambda item: str(item["value"]))
    return 0


def cmd_set(args) -> int:
    conn = storage.connect()
    try:
        value = settings.set_value(conn, args.key, args.value)
    finally:
        conn.close()

    output.emit(
        {"key": args.key, "value": value, "source": "stored"},
        lambda item: f"{item['key']} = {item['value']}",
    )
    return 0


def cmd_unset(args) -> int:
    conn = storage.connect()
    try:
        settings.unset_value(conn, args.key)
        value, source = settings.resolve(conn, args.key)
    finally:
        conn.close()

    output.emit(
        {"key": args.key, "value": value, "source": source},
        lambda item: f"{item['key']} = {item['value']} ({item['source']})",
    )
    return 0

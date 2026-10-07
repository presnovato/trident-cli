"""Typed settings on top of the storage layer.

A small registry maps each key to its type, default, validator and optional
environment override. Stored values are text in the ``settings`` table; the
effective value order is env override -> stored -> default.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from typing import Any, Callable

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from trident_cli import clock
from trident_cli.errors import EXIT_RUNTIME, EXIT_USAGE, CliError


# --- defaults ---------------------------------------------------------------


def _default_timezone() -> str:
    """Best-effort name of the system timezone, else ``UTC``."""
    name = os.environ.get("TZ")
    if name:
        try:
            ZoneInfo(name)
            return name
        except Exception:
            pass

    try:
        with open("/etc/timezone", encoding="utf-8") as fh:
            name = fh.read().strip()
        if name:
            try:
                ZoneInfo(name)
                return name
            except Exception:
                pass
    except OSError:
        pass

    try:
        resolved = os.path.realpath("/etc/localtime")
        marker = "zoneinfo/"
        index = resolved.find(marker)
        if index != -1:
            name = resolved[index + len(marker):]
            try:
                ZoneInfo(name)
                return name
            except Exception:
                pass
    except OSError:
        pass

    return system_offset()


def format_offset(delta: timedelta) -> str:
    """Render a UTC offset as ``+03:00`` / ``-05:30``."""
    sign = "-" if delta < timedelta(0) else "+"
    minutes = abs(int(delta.total_seconds())) // 60
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def system_offset() -> str:
    """The machine's current UTC offset, e.g. ``+03:00``.

    Windows exposes no IANA zone name and Python on Windows often has no tz
    database, but the local offset is always known. Falling back to ``UTC``
    instead would shift every Trident-day boundary by the local offset.
    """
    offset = clock.now().astimezone().utcoffset() or timedelta(0)
    return format_offset(offset)


def tzdata_available() -> bool:
    """Whether the IANA timezone database can be loaded at all."""
    try:
        ZoneInfo("UTC")
    except Exception:
        return False
    return True


# --- validators -------------------------------------------------------------

_FIXED_OFFSET_RE = re.compile(r"^(?:UTC)?([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def fixed_offset(name: str) -> timezone | None:
    """Parse ``UTC+03:00`` / ``+3`` style fixed offsets, else ``None``."""
    match = _FIXED_OFFSET_RE.match(name.strip())
    if not match:
        return None
    hours = int(match.group(2))
    minutes = int(match.group(3) or "0")
    if hours > 23 or minutes > 59:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    if match.group(1) == "-":
        delta = -delta
    return timezone(delta)


def validate_timezone(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValueError("timezone must not be empty")
    # Without a tz database (e.g. Windows without tzdata) only UTC and fixed
    # offsets load; to_tzinfo raises for anything else.
    to_tzinfo(name)
    return name


def to_tzinfo(name: str) -> tzinfo:
    """Turn a stored ``timezone`` value into a tzinfo object.

    Accepts IANA names (when a tz database is available), ``UTC`` and fixed
    offsets such as ``+03:00``. Never pass the raw setting to ``ZoneInfo``.
    """
    try:
        return ZoneInfo(name)
    except Exception:
        pass
    if name.strip().upper() == "UTC":
        return timezone.utc
    offset = fixed_offset(name)
    if offset is not None:
        return offset
    raise ValueError(f"unknown timezone: {name!r}")


def validate_day_open_hour(raw: str) -> int:
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise ValueError("day_open_hour must be an integer between 0 and 23")
    if not 0 <= value <= 23:
        raise ValueError("day_open_hour must be between 0 and 23")
    return value




@dataclass(frozen=True)
class Setting:
    key: str
    default: Any
    validate: Callable[[str], Any]
    env: str | None = None


SETTINGS: dict[str, Setting] = {
    "timezone": Setting("timezone", _default_timezone, validate_timezone),
    "day_open_hour": Setting("day_open_hour", 10, validate_day_open_hour),
}


# --- registry helpers -------------------------------------------------------


def keys() -> list[str]:
    return list(SETTINGS)


def _setting(key: str) -> Setting:
    if key not in SETTINGS:
        raise CliError(f"unknown setting: {key}", code=EXIT_USAGE)
    return SETTINGS[key]




def _default_value(setting: Setting) -> Any:
    default = setting.default
    return default() if callable(default) else default


# --- reads and writes -------------------------------------------------------


def resolve(conn: sqlite3.Connection, key: str) -> tuple[Any, str]:
    """Return ``(value, source)`` with source in ``env``/``stored``/``default``."""
    setting = _setting(key)

    if setting.env:
        raw = os.environ.get(setting.env)
        if raw is not None:
            try:
                return setting.validate(raw), "env"
            except ValueError as exc:
                raise CliError(f"invalid {setting.env}: {exc}", code=EXIT_RUNTIME) from exc

    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        try:
            return setting.validate(row[0]), "stored"
        except ValueError as exc:
            raise CliError(f"invalid stored value for {key}: {exc}", code=EXIT_RUNTIME) from exc

    return _default_value(setting), "default"


def list_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    result = []
    for key in SETTINGS:
        value, source = resolve(conn, key)
        result.append({"key": key, "value": value, "source": source})
    return result


def set_value(conn: sqlite3.Connection, key: str, raw: str) -> Any:
    setting = _setting(key)
    try:
        value = setting.validate(raw)
    except ValueError as exc:
        raise CliError(str(exc), code=EXIT_USAGE) from exc
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
    return value


def unset_value(conn: sqlite3.Connection, key: str) -> None:
    _setting(key)
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def user_tzinfo(conn: sqlite3.Connection) -> tzinfo:
    """The effective timezone as a tzinfo object — the only way code reads it."""
    value, _source = resolve(conn, "timezone")
    try:
        return to_tzinfo(value)
    except ValueError as exc:
        raise CliError(f"invalid timezone setting: {exc}", code=EXIT_RUNTIME) from exc

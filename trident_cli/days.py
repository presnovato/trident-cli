"""Trident-day arithmetic.

A Trident day runs from ``day_open_hour`` local time to the same hour the next
local day. A moment before the open hour belongs to the previous Trident day:
with the default 10:00, an entry at 01:30 on 3 October belongs to 2 October.

Pure module: no I/O, no clock, no settings. The caller passes an aware
``datetime`` and a ``tzinfo`` (see ``settings.user_tzinfo``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo


def trident_day(moment: datetime, tz: tzinfo, open_hour: int) -> date:
    """The Trident day a moment belongs to.

    ``moment`` must be timezone-aware; a naive datetime raises ``ValueError``.
    The moment is converted to ``tz`` and compared against the local open hour,
    so the result does not depend on the machine's own timezone.
    """
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("moment must be timezone-aware")

    local = moment.astimezone(tz)
    if local.hour < open_hour:
        return (local - timedelta(days=1)).date()
    return local.date()


def day_window(day: date, tz: tzinfo, open_hour: int) -> tuple[datetime, datetime]:
    """Aware UTC ``[start, end)`` of the Trident day.

    On a DST change the window is 23 or 25 hours; that is correct.
    """
    start = datetime(day.year, day.month, day.day, open_hour, tzinfo=tz)
    following = day + timedelta(days=1)
    end = datetime(following.year, following.month, following.day, open_hour, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

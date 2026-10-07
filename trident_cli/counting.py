"""The slow count: 10:1 conversion and season arithmetic.

Pure: no I/O, no clock, no settings, so it is unit-tested on its own.

One burst day changes little — that is the point of the 10:1 rounding up.
"""

from __future__ import annotations

from datetime import date, timedelta

DAYS_PER_SEASON = 28


def convert(points: int) -> int:
    """Convert day points to the next scale, 10:1 rounded up.

    ``0 -> 0``, ``1..10 -> 1``, ``11..20 -> 2``. Negative totals do not occur
    and convert to 0.
    """
    if points <= 0:
        return 0
    return -(-points // 10)


def season_day_number(start: date, day: date) -> int:
    """1-based position of ``day`` inside the season that starts on ``start``."""
    return (day - start).days + 1


def season_end(start: date) -> date:
    """The 28th and last day of the season that starts on ``start``."""
    return start + timedelta(days=DAYS_PER_SEASON - 1)


def season_start_for(day: date, first_start: date) -> date:
    """Start of the season that contains ``day``, given season 1's start.

    Seasons stay aligned to ``first_start``; after a long gap two seasons roll
    over at once rather than restarting on "today". A day before season 1 is
    clamped to ``first_start``.
    """
    if day < first_start:
        return first_start
    offset = (day - first_start).days
    return first_start + timedelta(days=(offset // DAYS_PER_SEASON) * DAYS_PER_SEASON)

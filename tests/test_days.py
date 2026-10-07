"""The Trident day: the open hour, fixed offsets and DST."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from trident_cli import days

UTC = timezone.utc
FIXED = timezone(timedelta(hours=3))


def test_before_the_open_hour_belongs_to_the_previous_day():
    moment = datetime(2026, 10, 3, 1, 30, tzinfo=FIXED)
    assert days.trident_day(moment, FIXED, 10) == date(2026, 10, 2)


def test_just_before_the_open_hour():
    moment = datetime(2026, 10, 3, 9, 59, tzinfo=FIXED)
    assert days.trident_day(moment, FIXED, 10) == date(2026, 10, 2)


def test_exactly_at_the_open_hour_is_the_new_day():
    moment = datetime(2026, 10, 3, 10, 0, tzinfo=FIXED)
    assert days.trident_day(moment, FIXED, 10) == date(2026, 10, 3)


def test_after_the_open_hour():
    moment = datetime(2026, 10, 3, 10, 1, tzinfo=FIXED)
    assert days.trident_day(moment, FIXED, 10) == date(2026, 10, 3)


def test_utc_zone():
    moment = datetime(2026, 10, 3, 9, 0, tzinfo=UTC)
    assert days.trident_day(moment, UTC, 10) == date(2026, 10, 2)


def test_moment_is_converted_to_the_given_zone():
    # 2026-10-02 23:00 UTC is 2026-10-03 02:00 in +03:00 — the previous Trident day.
    moment = datetime(2026, 10, 2, 23, 0, tzinfo=UTC)
    assert days.trident_day(moment, FIXED, 10) == date(2026, 10, 2)


def test_window_in_utc():
    start, end = days.day_window(date(2026, 10, 2), UTC, 10)
    assert start == datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 3, 10, 0, tzinfo=UTC)


def test_window_with_a_fixed_offset():
    start, end = days.day_window(date(2026, 10, 2), FIXED, 10)
    assert start == datetime(2026, 10, 2, 7, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 3, 7, 0, tzinfo=UTC)


def test_naive_moment_raises():
    with pytest.raises(ValueError, match="timezone-aware"):
        days.trident_day(datetime(2026, 10, 2, 12, 0), UTC, 10)


def test_dst_change_makes_a_23_or_25_hour_window():
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo("Europe/Berlin")
    except Exception:  # pragma: no cover - depends on the machine
        pytest.skip("no tz database on this machine")

    spring_start, spring_end = days.day_window(date(2026, 3, 28), tz, 10)
    assert (spring_end - spring_start) == timedelta(hours=23)

    autumn_start, autumn_end = days.day_window(date(2026, 10, 24), tz, 10)
    assert (autumn_end - autumn_start) == timedelta(hours=25)

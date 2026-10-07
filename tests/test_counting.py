"""The pure slow count: 10:1 conversion and season arithmetic."""

from __future__ import annotations

from datetime import date

import pytest

from trident_cli import counting

CASES = {
    0: 0,
    1: 1,
    9: 1,
    10: 1,
    11: 2,
    20: 2,
    21: 3,
    25: 3,
    30: 3,
}


@pytest.mark.parametrize("points, expected", sorted(CASES.items()))
def test_convert(points, expected):
    assert counting.convert(points) == expected


def test_convert_negative_is_zero():
    assert counting.convert(-5) == 0


def test_season_day_number():
    start = date(2026, 9, 1)
    assert counting.season_day_number(start, date(2026, 9, 1)) == 1
    assert counting.season_day_number(start, date(2026, 9, 28)) == 28
    assert counting.season_day_number(start, date(2026, 9, 29)) == 29


def test_season_end():
    assert counting.season_end(date(2026, 9, 1)) == date(2026, 9, 28)
    assert counting.season_end(date(2026, 9, 29)) == date(2026, 10, 26)


def test_season_start_for_is_aligned():
    first = date(2026, 9, 1)
    assert counting.season_start_for(date(2026, 9, 1), first) == date(2026, 9, 1)
    assert counting.season_start_for(date(2026, 9, 28), first) == date(2026, 9, 1)
    assert counting.season_start_for(date(2026, 9, 29), first) == date(2026, 9, 29)
    assert counting.season_start_for(date(2026, 10, 26), first) == date(2026, 9, 29)
    assert counting.season_start_for(date(2026, 10, 27), first) == date(2026, 10, 27)


def test_season_start_for_clamps_before_the_first_season():
    first = date(2026, 9, 1)
    assert counting.season_start_for(date(2026, 8, 1), first) == first

"""The entry parser: text, pairs, aliases and the error cases."""

from __future__ import annotations

import pytest

from trident_cli import parser
from trident_cli.parser import ParseError, ParsedEntry


def test_plain_text_has_no_attributes():
    result = parser.parse_entry("ничего особенного")
    assert result == ParsedEntry(text="ничего особенного")
    assert result.has_attributes is False


def test_trailing_pairs_are_taken_from_the_end():
    result = parser.parse_entry("Ran 5k +2 STR +1 WILL")
    assert result.text == "Ran 5k"
    assert (result.str_points, result.agi_points, result.int_points, result.will_points) == (2, 0, 0, 1)
    assert result.has_attributes is True


def test_attribute_then_points_order():
    result = parser.parse_entry("Read a chapter\nINT +2")
    assert result.text == "Read a chapter"
    assert result.int_points == 2


def test_attribute_line_with_several_pairs():
    result = parser.parse_entry("Long day\n+1 STR +1 WILL")
    assert result.text == "Long day"
    assert result.str_points == 1
    assert result.will_points == 1


def test_aliases_and_mixed_case():
    result = parser.parse_entry("Ran +2 ТЕЛО +1 воля")
    assert result.text == "Ran"
    assert result.str_points == 2
    assert result.will_points == 1


def test_alias_attribute_line():
    result = parser.parse_entry("Read\nЛЮДИ +3")
    assert result.text == "Read"
    assert result.agi_points == 3


def test_multiline_text_keeps_internal_blank_lines():
    result = parser.parse_entry("first\n\nsecond")
    assert result.text == "first\n\nsecond"


def test_trailing_blank_lines_are_dropped():
    result = parser.parse_entry("first\n\n\n")
    assert result.text == "first"


def test_text_before_an_attribute_line_is_kept():
    result = parser.parse_entry("Read a chapter\n+2 INT")
    assert result.text == "Read a chapter"
    assert result.int_points == 2


def test_pair_in_the_middle_stays_text():
    assert parser.parse_entry("Read +2 INT notes").text == "Read +2 INT notes"
    assert parser.parse_entry("Read +2 INT notes").has_attributes is False
    assert parser.parse_entry("Gave +2 INT talk").text == "Gave +2 INT talk"


def test_internal_spacing_before_pairs_is_preserved():
    result = parser.parse_entry("Ran    5k   +2 STR")
    assert result.text == "Ran    5k"
    assert result.str_points == 2


@pytest.mark.parametrize("raw", ["+4 STR", "Ran +4 STR", "INT +4"])
def test_points_above_three_are_an_error(raw):
    with pytest.raises(ParseError, match="points must be 1–3"):
        parser.parse_entry(raw)


@pytest.mark.parametrize("raw", ["+0 INT", "Ran +0 INT", "STR +0"])
def test_zero_points_are_an_error(raw):
    with pytest.raises(ParseError, match="points must be 1–3"):
        parser.parse_entry(raw)


@pytest.mark.parametrize("raw", ["-1 STR", "Ran -1 STR", "AGI -1"])
def test_negative_points_are_an_error(raw):
    with pytest.raises(ParseError, match="points must be 1–3"):
        parser.parse_entry(raw)


@pytest.mark.parametrize("raw", ["+1 STR +2 ТЕЛО", "Ran 5k +1 STR +2 str", "ВОЛЯ +1 +2 WILL"])
def test_duplicate_attribute_is_an_error(raw):
    with pytest.raises(ParseError, match="at most once"):
        parser.parse_entry(raw)


def test_text_after_an_attribute_line_is_an_error():
    with pytest.raises(ParseError, match="text after attributes"):
        parser.parse_entry("Ran\n+2 INT\nmore text")


@pytest.mark.parametrize("raw", ["", "   ", "\n\n"])
def test_empty_text_is_an_error(raw):
    with pytest.raises(ParseError, match="write what happened"):
        parser.parse_entry(raw)


@pytest.mark.parametrize("raw", ["+2 INT", "+1 STR\n+1 WILL"])
def test_only_pairs_without_text_is_an_error(raw):
    with pytest.raises(ParseError, match="write what happened"):
        parser.parse_entry(raw)


def test_over_long_text_is_an_error():
    with pytest.raises(ParseError, match="too long"):
        parser.parse_entry("x" * (parser.MAX_TEXT + 1))


def test_text_at_the_limit_is_kept():
    result = parser.parse_entry("x" * parser.MAX_TEXT)
    assert len(result.text) == parser.MAX_TEXT

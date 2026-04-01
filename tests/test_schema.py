"""Tests for schema.py — structural assertions on EVENT_INPUT_SCHEMA."""

from drag_events import extract
from drag_events import extract_text
from drag_events import schema
from drag_events.schema import EVENT_INPUT_SCHEMA


def test_required_fields():
    assert set(EVENT_INPUT_SCHEMA["required"]) == {"title", "event_type", "track", "dates", "confidence"}


def test_event_type_enum():
    expected = {"bracket", "points_race", "test_n_tune", "no_prep", "grudge", "specialty", "test_day", "unknown"}
    actual = set(EVENT_INPUT_SCHEMA["properties"]["event_type"]["enum"])
    assert actual == expected


def test_track_nested_required():
    assert EVENT_INPUT_SCHEMA["properties"]["track"]["required"] == ["name"]


def test_dates_nested_required():
    assert EVENT_INPUT_SCHEMA["properties"]["dates"]["required"] == ["start"]


def test_confidence_bounds():
    conf = EVENT_INPUT_SCHEMA["properties"]["confidence"]
    assert conf["minimum"] == 0
    assert conf["maximum"] == 1


def test_extract_tool_uses_shared_schema():
    """Regression: extract.py must reference schema.EVENT_INPUT_SCHEMA, not a copy."""
    assert extract.TOOL["input_schema"] is EVENT_INPUT_SCHEMA


def test_extract_text_tool_uses_shared_schema():
    """Regression: extract_text.py must reference schema.EVENT_INPUT_SCHEMA, not a copy."""
    assert extract_text.TOOL["input_schema"] is EVENT_INPUT_SCHEMA

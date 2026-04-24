"""Tests for validating dist/events.json against the published schema."""

import copy

import pytest

from drag_events.flyer_processing import pipeline as flyer_processing
from drag_events.event_validation.cli import SchemaValidationError, validate_events_payload


def test_validate_events_payload_accepts_sample_events(sample_events):
    validate_events_payload(sample_events)


def test_validate_events_payload_rejects_missing_required_field(sample_events):
    invalid = copy.deepcopy(sample_events)
    invalid[0].pop("confidence")

    with pytest.raises(SchemaValidationError) as excinfo:
        validate_events_payload(invalid)

    assert "$[0]" in str(excinfo.value)
    assert "missing required property 'confidence'" in str(excinfo.value)


def test_validate_events_payload_rejects_invalid_uri(sample_events):
    invalid = copy.deepcopy(sample_events)
    invalid[0]["contact"]["website"] = "example.com"

    with pytest.raises(SchemaValidationError) as excinfo:
        validate_events_payload(invalid)

    assert "$[0].contact.website" in str(excinfo.value)
    assert "expected uri string" in str(excinfo.value).lower()


def test_save_events_rejects_schema_invalid_output(tmp_events_file, sample_events):
    invalid = copy.deepcopy(sample_events)
    invalid[0].pop("confidence")

    with pytest.raises(SchemaValidationError):
        flyer_processing.save_events(invalid)

    assert not tmp_events_file.exists()



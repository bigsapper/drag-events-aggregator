"""Tests for flyer_processing — flyer processing orchestration."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from drag_events.flyer_processing import cli as flyer_processing
from tests.conftest import SAMPLE_EVENT_ID, make_1x1_png

PROJECT_DIR = Path(__file__).parent.parent


# ── load_events / save_events ─────────────────────────────────────────────────

def test_load_events_missing_file(tmp_events_file):
    assert flyer_processing.load_events() == []


def test_load_events_existing_file(tmp_events_file, sample_events):
    tmp_events_file.write_text(json.dumps(sample_events))
    result = flyer_processing.load_events()
    assert len(result) == 1
    assert result[0]["id"] == SAMPLE_EVENT_ID


def test_save_events_writes_valid_json(tmp_events_file, sample_events):
    flyer_processing.save_events(sample_events)
    raw = json.loads(tmp_events_file.read_text())
    assert len(raw) == 1


def test_save_events_roundtrip(tmp_events_file, sample_events):
    flyer_processing.save_events(sample_events)
    loaded = flyer_processing.load_events()
    assert loaded == sample_events


# ── collect_images ────────────────────────────────────────────────────────────

def test_collect_images_single_file(tmp_path):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    result = flyer_processing.collect_images([str(img)])
    assert img in result


def test_collect_images_directory(tmp_path):
    make_1x1_png(tmp_path / "a.jpg")
    make_1x1_png(tmp_path / "b.png")
    make_1x1_png(tmp_path / "c.webp")
    result = flyer_processing.collect_images([str(tmp_path)])
    assert len(result) == 3


def test_collect_images_skips_non_image(tmp_path, capsys):
    txt = tmp_path / "notes.txt"
    txt.write_text("not an image")
    result = flyer_processing.collect_images([str(txt)])
    assert result == []
    assert "Skipping" in capsys.readouterr().out


def test_collect_images_deduplicates(tmp_path):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    result = flyer_processing.collect_images([str(img), str(img)])
    assert len(result) == 1


def test_collect_images_returns_sorted(tmp_path):
    make_1x1_png(tmp_path / "b.jpg")
    make_1x1_png(tmp_path / "a.jpg")
    result = flyer_processing.collect_images([str(tmp_path)])
    names = [p.name for p in result]
    assert names == sorted(names)


# ── process_flyer ─────────────────────────────────────────────────────────────

def test_process_flyer_duplicate(tmp_path, sample_events):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="aabbccdd00112233"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=sample_events[0]):
        outcome, event = flyer_processing.process_flyer(str(img), sample_events)
    assert outcome == "duplicate"
    assert event["id"] == SAMPLE_EVENT_ID


def test_process_flyer_duplicate_skips_claude(tmp_path, sample_events, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="aabbccdd00112233"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=sample_events[0]):
        flyer_processing.process_flyer(str(img), sample_events)
    mock_vision_client.assert_not_called()


def test_process_flyer_new_event(tmp_path, sample_events, mock_vision_client, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        outcome, event = flyer_processing.process_flyer(str(img), sample_events)
    assert outcome == "new"
    assert "id" in event
    assert event["title"] == sample_extracted["title"]
    assert len(sample_events) == 2


def test_process_flyer_new_event_has_flyer_entry(tmp_path, sample_events, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        _, event = flyer_processing.process_flyer(str(img), sample_events)
    assert len(event["flyers"]) == 1
    assert event["flyers"][0]["file"] == img.name


def test_process_flyer_normalizes_contact_website(tmp_path, sample_events):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    extracted = {
        "title": "Street Car Takeover Dallas",
        "event_type": "specialty",
        "series": None,
        "track": {"name": "Texas Motorplex", "city": "Ennis", "state": "TX"},
        "dates": {"start": "2026-05-01", "end": "2026-05-02"},
        "times": {"gates_open": None, "registration_opens": None, "race_start": None},
        "classes": ["Street"],
        "fees": {"entry": None, "spectator": None},
        "contact": {"phone": None, "email": None, "website": "streetcartakeover.com"},
        "confidence": 0.9,
        "unclear_fields": [],
        "notes": None,
    }
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.extract_event", return_value=extracted), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        _, event = flyer_processing.process_flyer(str(img), sample_events)
    assert event["contact"]["website"] == "https://streetcartakeover.com"


def test_process_flyer_merged(tmp_path, sample_events, mock_vision_client, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=sample_events[0]):
        outcome, event = flyer_processing.process_flyer(str(img), sample_events)
    assert outcome == "merged"
    assert len(sample_events[0]["flyers"]) == 2


def test_process_flyer_skips_out_of_scope_event(tmp_path, sample_events, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.extract_event", return_value={"title": "2026 TMCCC Banquet", "track": {}, "dates": {"start": "2026-12-05"}}):
        outcome, event = flyer_processing.process_flyer(str(img), sample_events)
    assert outcome == "skipped"
    assert event["title"] == "2026 TMCCC Banquet"
    assert len(sample_events) == 1


def test_process_flyer_skips_past_event(tmp_path, sample_events, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.extract_event", return_value={"title": "Old Flyer", "track": {}, "dates": {"start": "2025-01-01"}}):
        outcome, event = flyer_processing.process_flyer(str(img), sample_events)
    assert outcome == "skipped"
    assert event["title"] == "Old Flyer"
    assert len(sample_events) == 1


# ── main() ────────────────────────────────────────────────────────────────────

def test_main_no_args_exits(capsys):
    with patch.object(sys, "argv", ["flyer_processing.py"]):
        with pytest.raises(SystemExit):
            flyer_processing.main()


def test_main_no_images_found_exits(tmp_path, capsys):
    with patch.object(sys, "argv", ["flyer_processing.py", str(tmp_path)]):
        with pytest.raises(SystemExit):
            flyer_processing.main()


def test_main_processes_image_and_saves(tmp_path, tmp_events_file, mock_vision_client, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch.object(sys, "argv", ["flyer_processing.py", str(img)]), \
         patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        flyer_processing.main()
    events = flyer_processing.load_events()
    assert len(events) == 1


def test_main_deletes_processed_image(tmp_path, tmp_events_file, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    assert img.exists()
    with patch.object(sys, "argv", ["flyer_processing.py", str(img)]), \
         patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        flyer_processing.main()
    assert not img.exists()


def test_main_preserves_test_flyer(tmp_events_file, mock_vision_client):
    """Files inside test-flyers/ must not be deleted after processing."""
    img = PROJECT_DIR / "tests" / "test-flyers" / "bad-boys-mayhem.jpg"
    assert img.exists()
    with patch.object(sys, "argv", ["flyer_processing.py", str(img)]), \
         patch("drag_events.flyer_processing.cli.compute_phash", return_value="00000000ffffffff"), \
         patch("drag_events.flyer_processing.cli.is_duplicate_image", return_value=None), \
         patch("drag_events.flyer_processing.cli.find_same_event", return_value=None):
        flyer_processing.main()
    assert img.exists()


def test_main_counts_errors(tmp_path, tmp_events_file, capsys):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch.object(sys, "argv", ["flyer_processing.py", str(img)]), \
         patch("drag_events.flyer_processing.cli.compute_phash", side_effect=RuntimeError("boom")):
        flyer_processing.main()
    out = capsys.readouterr().out
    assert "1 errors" in out or "error" in out.lower()



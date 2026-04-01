import os

# Must be set before any project module is imported, because extract.py and
# extract_text.py create anthropic.Anthropic(api_key=...) at module scope.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-for-testing")

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_DIR = Path(__file__).parent.parent
TEST_FLYERS_DIR = PROJECT_DIR / "tests" / "test-flyers"


# ── Shared event data ─────────────────────────────────────────────────────────

@pytest.fixture
def sample_extracted():
    """Minimal extracted event dict as returned by Claude."""
    return {
        "title": "Spring Bracket Classic",
        "event_type": "bracket",
        "series": None,
        "track": {"name": "Texas Motorplex", "city": "Ennis", "state": "TX"},
        "dates": {"start": "2026-05-10", "end": None},
        "times": {"gates_open": "08:00", "registration_opens": "09:00", "race_start": "11:00"},
        "classes": ["Super Pro", "Pro"],
        "fees": {"entry": "$60/class", "spectator": "$15"},
        "contact": {"phone": "972-878-2641", "email": None, "website": None},
        "confidence": 0.92,
        "unclear_fields": [],
        "notes": None,
    }


@pytest.fixture
def sample_events(sample_extracted):
    """One existing event in the database."""
    return [
        {
            "id": "evt-001",
            **sample_extracted,
            "flyers": [{"file": "flyer1.jpg", "phash": "aabbccdd00112233", "processed_at": "2026-01-01T00:00:00+00:00"}],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]


# ── Claude API mocks ──────────────────────────────────────────────────────────

def _make_tool_response(event_data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "store_event"
    block.input = event_data
    response = MagicMock()
    response.content = [block]
    return response


@pytest.fixture
def mock_vision_client(sample_extracted):
    """Patch extract.CLIENT.messages.create with a canned vision response."""
    with patch("extract.CLIENT.messages.create", return_value=_make_tool_response(sample_extracted)) as m:
        yield m


@pytest.fixture
def mock_text_client(sample_extracted):
    """Patch extract_text.CLIENT.messages.create with a canned text response."""
    with patch("extract_text.CLIENT.messages.create", return_value=_make_tool_response(sample_extracted)) as m:
        yield m


# ── File-system redirects ─────────────────────────────────────────────────────

@pytest.fixture
def tmp_events_file(tmp_path, monkeypatch):
    import process
    path = tmp_path / "events.json"
    monkeypatch.setattr(process, "EVENTS_FILE", path)
    return path


@pytest.fixture
def tmp_crawl_state(tmp_path, monkeypatch):
    import crawl
    path = tmp_path / ".crawl_state.json"
    monkeypatch.setattr(crawl, "CRAWL_STATE", path)
    return path


@pytest.fixture
def tmp_flyers_dir(tmp_path, monkeypatch):
    import crawl
    flyers = tmp_path / "flyers"
    flyers.mkdir()
    monkeypatch.setattr(crawl, "FLYERS_DIR", flyers)
    return flyers


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_1x1_png(path: Path) -> Path:
    """Write a minimal 1×1 white PNG to path and return it."""
    from PIL import Image
    img = Image.new("RGB", (1, 1), color=(255, 255, 255))
    img.save(path)
    return path

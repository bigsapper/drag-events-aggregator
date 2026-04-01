"""Tests for dedup.py."""

import pytest
from pathlib import Path

from drag_events import dedup
from drag_events.dedup import (
    compute_phash,
    phash_distance,
    is_duplicate_image,
    find_same_event,
    merge_events,
    track_slug,
    _parse_date,
    _dates_overlap,
    _normalize_track_name,
    _resolve_canonical,
    _tracks_match,
)

PROJECT_DIR = Path(__file__).parent.parent
TEST_FLYERS = PROJECT_DIR / "tests" / "test-flyers"


# ── compute_phash / phash_distance ────────────────────────────────────────────

def test_compute_phash_returns_hex_string():
    img = TEST_FLYERS / "bad-boys-mayhem.jpg"
    result = compute_phash(str(img))
    assert isinstance(result, str)
    assert len(result) > 0


def test_phash_distance_identical():
    img = TEST_FLYERS / "bad-boys-mayhem.jpg"
    h = compute_phash(str(img))
    assert phash_distance(h, h) == 0


def test_phash_distance_different_images():
    h1 = compute_phash(str(TEST_FLYERS / "bad-boys-mayhem.jpg"))
    h2 = compute_phash(str(TEST_FLYERS / "xtreme-bracket-series.jpg"))
    assert phash_distance(h1, h2) > 0


def test_phash_distance_same_hash_string():
    h = "f" * 16
    assert phash_distance(h, h) == 0


def test_phash_distance_all_zeros_vs_all_ones():
    h_zero = "0" * 16
    h_ones = "f" * 16
    assert phash_distance(h_zero, h_ones) > 0


# ── is_duplicate_image ────────────────────────────────────────────────────────

def test_is_duplicate_image_exact_match():
    img = TEST_FLYERS / "bad-boys-mayhem.jpg"
    h = compute_phash(str(img))
    events = [{"id": "1", "flyers": [{"phash": h}]}]
    result = is_duplicate_image(h, events)
    assert result is not None
    assert result["id"] == "1"


def test_is_duplicate_image_no_match():
    events = [{"id": "1", "flyers": [{"phash": "0" * 16}]}]
    assert is_duplicate_image("f" * 16, events) is None


def test_is_duplicate_image_empty_events():
    assert is_duplicate_image("0" * 16, []) is None


def test_is_duplicate_image_null_phash_skipped():
    events = [{"id": "1", "flyers": [{"phash": None}]}]
    assert is_duplicate_image("0" * 16, events) is None


def test_is_duplicate_image_no_flyers_key():
    events = [{"id": "1"}]
    assert is_duplicate_image("0" * 16, events) is None


# ── _parse_date ───────────────────────────────────────────────────────────────

def test_parse_date_valid():
    from datetime import date
    assert _parse_date("2025-04-12") == date(2025, 4, 12)


def test_parse_date_none():
    assert _parse_date(None) is None


def test_parse_date_empty_string():
    assert _parse_date("") is None


def test_parse_date_invalid():
    assert _parse_date("not-a-date") is None


# ── _dates_overlap ────────────────────────────────────────────────────────────

def _ev(start, end=None):
    d = {"start": start}
    if end:
        d["end"] = end
    return {"dates": d}


def test_dates_overlap_same_day():
    assert _dates_overlap(_ev("2025-04-12"), _ev("2025-04-12"))


def test_dates_overlap_range():
    assert _dates_overlap(_ev("2025-04-10", "2025-04-13"), _ev("2025-04-12", "2025-04-15"))


def test_dates_overlap_adjacent_no_overlap():
    assert not _dates_overlap(_ev("2025-04-10", "2025-04-11"), _ev("2025-04-12", "2025-04-13"))


def test_dates_overlap_single_day_within_range():
    assert _dates_overlap(_ev("2025-04-10", "2025-04-15"), _ev("2025-04-12"))


def test_dates_overlap_missing_start():
    assert not _dates_overlap({"dates": {}}, _ev("2025-04-12"))


def test_dates_overlap_both_missing():
    assert not _dates_overlap({"dates": {}}, {"dates": {}})


# ── _normalize_track_name ─────────────────────────────────────────────────────

def test_normalize_removes_raceway():
    assert _normalize_track_name("Tulsa Raceway Park") == "tulsa"


def test_normalize_removes_drag_strip():
    assert _normalize_track_name("Yello Belly Drag Strip") == "yello belly"


def test_normalize_keeps_meaningful_words():
    result = _normalize_track_name("Texas Motorplex")
    assert "texas" in result
    assert "motorplex" in result


def test_normalize_case_insensitive():
    a = _normalize_track_name("XTREME RACEWAY PARK")
    b = _normalize_track_name("xtreme raceway park")
    assert a == b


# ── _tracks_match ─────────────────────────────────────────────────────────────

def _track_ev(name, state=None):
    t = {"name": name}
    if state:
        t["state"] = state
    return {"track": t}


def test_tracks_match_exact():
    assert _tracks_match(_track_ev("Texas Motorplex", "TX"), _track_ev("Texas Motorplex", "TX"))


def test_tracks_match_after_normalization():
    assert _tracks_match(_track_ev("Tulsa Raceway Park"), _track_ev("Tulsa Raceway"))


def test_tracks_match_substring():
    assert _tracks_match(_track_ev("Gainesville Raceway"), _track_ev("Gainesville Regional Raceway Park"))


def test_tracks_match_shared_tokens():
    assert _tracks_match(_track_ev("Dallas Motorplex Racing"), _track_ev("Dallas Motorplex"))


def test_tracks_no_match_different_names():
    assert not _tracks_match(_track_ev("Texas Motorplex"), _track_ev("Tulsa Raceway Park"))


def test_tracks_no_match_empty_name():
    assert not _tracks_match(_track_ev(""), _track_ev("Texas Motorplex"))


def test_tracks_state_mismatch_blocks_token_match():
    # Identical names but different states → False
    a = {"track": {"name": "Dallas Motorplex Racing", "state": "TX"}}
    b = {"track": {"name": "Dallas Motorplex Racing", "state": "CA"}}
    assert _tracks_match(a, b) is False


def test_tracks_state_null_does_not_crash():
    """state: null (explicit None) must not raise AttributeError on .upper() (line 84)."""
    a = {"track": {"name": "Little River Dragway", "state": None}}
    b = {"track": {"name": "Little River Dragway", "state": None}}
    assert _tracks_match(a, b) is True


def test_tracks_state_mismatch_blocks_token_match_on_distinct_names():
    """Shared tokens + differing states → False (line 84 reachable when names are distinct)."""
    # Use distinct names that share 2+ tokens but do NOT normalize to identical strings
    # so the early exact/substring returns are skipped and state is checked.
    a = {"track": {"name": "Oklahoma City Thunder Raceway", "state": "OK"}}
    b = {"track": {"name": "Texas City Thunder Raceway",   "state": "TX"}}
    assert _tracks_match(a, b) is False


# ── track_slug ───────────────────────────────────────────────────────────────

def test_track_slug_name_and_state():
    # "motorplex" is not a stopword, so it survives normalization
    assert track_slug("Texas Motorplex", "TX") == "texas-motorplex-tx"

def test_track_slug_name_only():
    # "dragway" is not a stopword; "drag" alone is but it doesn't match "dragway"
    assert track_slug("Little River Dragway", None) == "little-river-dragway"

def test_track_slug_normalizes_variants():
    # Both "Xtreme Raceway Park" and "Xtreme Raceway" normalize to "xtreme" → same slug
    assert track_slug("Xtreme Raceway Park", "TX") == track_slug("Xtreme Raceway", "TX")

def test_track_slug_none_name():
    assert track_slug(None, "TX") is None

def test_track_slug_state_lowercased():
    # "raceway" and "park" are stopwords → "thunder valley"
    assert track_slug("Thunder Valley Raceway Park", "OK") == "thunder-valley-ok"


# ── alias resolution ─────────────────────────────────────────────────────────

@pytest.fixture()
def alias_map(monkeypatch):
    """Install a known alias map for tests that need it."""
    monkeypatch.setattr(dedup, "_ALIAS_MAP", {"xrp": "Xtreme Raceway Park", "xtreme raceway": "Xtreme Raceway Park"})


def test_load_alias_map_missing_file(monkeypatch, tmp_path):
    """Returns empty dict when track_aliases.json does not exist (line 25)."""
    monkeypatch.setattr(dedup, "_ALIASES_FILE", tmp_path / "nonexistent.json")
    assert dedup._load_alias_map() == {}

def test_resolve_canonical_known_alias(alias_map):
    assert _resolve_canonical("XRP") == "Xtreme Raceway Park"

def test_resolve_canonical_case_insensitive(alias_map):
    assert _resolve_canonical("xrp") == "Xtreme Raceway Park"

def test_resolve_canonical_unknown_returns_original(alias_map):
    assert _resolve_canonical("Texas Motorplex") == "Texas Motorplex"

def test_alias_match_abbreviation_and_full_name(alias_map):
    """'XRP' and 'Xtreme Raceway Park' should match as the same track."""
    a = {"track": {"name": "XRP", "state": "TX"}}
    b = {"track": {"name": "Xtreme Raceway Park", "state": "TX"}}
    assert _tracks_match(a, b) is True

def test_alias_slug_matches_canonical_slug(alias_map):
    """Alias and canonical name produce the same track.id slug."""
    assert track_slug("XRP", "TX") == track_slug("Xtreme Raceway Park", "TX")


# ── find_same_event ───────────────────────────────────────────────────────────

def test_find_same_event_match(sample_events):
    new = {"track": {"name": "Texas Motorplex", "state": "TX"}, "dates": {"start": "2026-05-10"}}
    result = find_same_event(new, sample_events)
    assert result is not None
    assert result["id"] == "evt-001"


def test_find_same_event_no_track_match(sample_events):
    new = {"track": {"name": "Tulsa Raceway Park"}, "dates": {"start": "2026-05-10"}}
    assert find_same_event(new, sample_events) is None


def test_find_same_event_no_date_overlap(sample_events):
    new = {"track": {"name": "Texas Motorplex", "state": "TX"}, "dates": {"start": "2026-06-01"}}
    assert find_same_event(new, sample_events) is None


def test_find_same_event_empty_db():
    new = {"track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}}
    assert find_same_event(new, []) is None


# ── merge_events ──────────────────────────────────────────────────────────────

@pytest.fixture
def existing():
    return {
        "id": "evt-001",
        "title": "Old Title",
        "event_type": "bracket",
        "series": None,
        "track": {"name": "Texas Motorplex", "city": None, "state": "TX"},
        "dates": {"start": "2026-05-10", "end": None},
        "times": {"gates_open": None, "registration_opens": None, "race_start": None},
        "fees": {"entry": None, "spectator": None},
        "contact": {"phone": None, "email": None, "website": None},
        "classes": ["Super Pro"],
        "confidence": 0.6,
        "flyers": [{"file": "old.jpg", "phash": "abc", "processed_at": "2026-01-01T00:00:00+00:00"}],
        "notes": None,
    }


@pytest.fixture
def new_flyer():
    return {"file": "new.jpg", "phash": "def", "processed_at": "2026-02-01T00:00:00+00:00"}


def test_merge_new_title_wins(existing, new_flyer):
    new_data = {"title": "Updated Title", "track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["title"] == "Updated Title"


def test_merge_null_new_does_not_overwrite(existing, new_flyer):
    new_data = {"title": None, "track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["title"] == "Old Title"


def test_merge_classes_union(existing, new_flyer):
    new_data = {"classes": ["Super Pro", "Pro"], "track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert set(merged["classes"]) == {"Super Pro", "Pro"}


def test_merge_confidence_max(existing, new_flyer):
    new_data = {"track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.95}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["confidence"] == 0.95


def test_merge_flyer_appended(existing, new_flyer):
    new_data = {"track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert len(merged["flyers"]) == 2
    assert merged["flyers"][-1]["file"] == "new.jpg"


def test_merge_track_fills_missing_city(existing, new_flyer):
    new_data = {"track": {"name": "Texas Motorplex", "city": "Ennis", "state": "TX"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["track"]["city"] == "Ennis"
    assert merged["track"]["id"] == track_slug("Texas Motorplex", "TX")


def test_merge_track_id_set_on_merge(existing, new_flyer):
    new_data = {"track": {"name": "Texas Motorplex", "state": "TX"}, "dates": {"start": "2026-05-10"}, "confidence": 0.9}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["track"]["id"] == track_slug("Texas Motorplex", "TX")


def test_merge_preserves_id(existing, new_flyer):
    new_data = {"track": {"name": "Texas Motorplex"}, "dates": {"start": "2026-05-10"}, "confidence": 0.7}
    merged = merge_events(existing, new_data, new_flyer)
    assert merged["id"] == "evt-001"

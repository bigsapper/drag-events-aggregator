"""Deduplication logic for drag racing event flyers.

Two-layer dedup:
  1. Image-level: perceptual hash catches the same flyer shared across platforms
  2. Event-level: same track + overlapping dates = same event, merge records
"""

import json
import re

import imagehash
from PIL import Image
from datetime import date
from pathlib import Path

# Hamming distance threshold — hashes within this distance are the same image
PHASH_THRESHOLD = 10

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "src" / "config"
_ALIASES_FILE = CONFIG_DIR / "track_aliases.json"


def _load_alias_map() -> dict[str, str]:
    """Build a lowercase alias -> canonical name lookup from track_aliases.json."""
    if not _ALIASES_FILE.exists():
        return {}
    entries = json.loads(_ALIASES_FILE.read_text())
    return {alias.lower(): entry["canonical"]
            for entry in entries
            for alias in entry.get("aliases", [])}


_ALIAS_MAP: dict[str, str] = _load_alias_map()


def _resolve_canonical(name: str) -> str:
    """Substitute a known alias with its canonical track name."""
    return _ALIAS_MAP.get(name.strip().lower(), name)


def compute_phash(image_path: str) -> str:
    img = Image.open(image_path)
    return str(imagehash.phash(img))


def phash_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def is_duplicate_image(new_hash: str, events: list[dict]) -> dict | None:
    """Return the existing event if new_hash matches any stored flyer hash."""
    for event in events:
        for flyer in event.get("flyers", []):
            stored_hash = flyer.get("phash")
            if stored_hash and phash_distance(new_hash, stored_hash) <= PHASH_THRESHOLD:
                return event
    return None


def _parse_date(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


def _dates_overlap(event_a: dict, event_b: dict) -> bool:
    """Return True if two events share at least one calendar day."""
    a_start = _parse_date(event_a.get("dates", {}).get("start"))
    a_end = _parse_date(event_a.get("dates", {}).get("end")) or a_start
    b_start = _parse_date(event_b.get("dates", {}).get("start"))
    b_end = _parse_date(event_b.get("dates", {}).get("end")) or b_start

    if not all([a_start, b_start]):
        return False

    return a_start <= b_end and b_start <= a_end


def track_slug(name: str | None, state: str | None) -> str | None:
    """Generate a stable URL-safe slug for a track (e.g. 'texas-motorplex-tx').

    Uses the same normalization as track matching so name variants like
    'Xtreme Raceway Park' and 'Xtreme Raceway' produce the same slug.
    Used as track.id in events.json so consumers can filter by track without
    fuzzy-matching name strings.
    """
    if not name:
        return None
    normalized = _normalize_track_name(_resolve_canonical(name))
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    if state:
        slug = f"{slug}-{state.lower()}"
    return slug or None


def _normalize_track_name(name: str) -> str:
    """Lowercase, strip common suffixes for fuzzy matching."""
    stopwords = ["raceway", "race", "way", "park", "dragstrip", "drag", "strip", "motorsports", "the"]
    words = name.lower().split()
    return " ".join(w for w in words if w not in stopwords).strip()


def _tracks_match(event_a: dict, event_b: dict) -> bool:
    name_a = _normalize_track_name(_resolve_canonical(event_a.get("track", {}).get("name", "")))
    name_b = _normalize_track_name(_resolve_canonical(event_b.get("track", {}).get("name", "")))

    if not name_a or not name_b:
        return False

    # State must match if both present — check before name comparison to avoid
    # false positives across states even when names are identical.
    state_a = (event_a.get("track", {}).get("state") or "").upper()
    state_b = (event_b.get("track", {}).get("state") or "").upper()
    if state_a and state_b and state_a != state_b:
        return False

    # Exact match after normalization
    if name_a == name_b:
        return True

    # One is a substring of the other (handles abbreviations like "GRP" vs "Gainesville Regional Park")
    if name_a in name_b or name_b in name_a:
        return True

    # Shared token count — if 2+ meaningful words in common, likely same track
    tokens_a = set(name_a.split())
    tokens_b = set(name_b.split())
    return len(tokens_a & tokens_b) >= 2


def find_same_event(new_event: dict, events: list[dict]) -> dict | None:
    """Return existing event record if new_event is the same event (different flyer)."""
    for event in events:
        if _tracks_match(new_event, event) and _dates_overlap(new_event, event):
            return event
    return None


def merge_events(existing: dict, new_data: dict, new_flyer_entry: dict) -> dict:
    """Merge new flyer data into an existing event record.

    Strategy: newer flyer is authoritative for non-null fields.
    Additive for classes (union). Append to flyers list.
    """
    merged = dict(existing)

    # Scalar fields — new value wins if present
    for field in ("title", "event_type", "series", "notes"):
        if new_data.get(field):
            merged[field] = new_data[field]

    # Track — new values fill in missing fields
    existing_track = existing.get("track", {})
    new_track = new_data.get("track", {})
    merged_name  = new_track.get("name")  or existing_track.get("name")
    merged_state = new_track.get("state") or existing_track.get("state")
    merged["track"] = {
        "id":    track_slug(merged_name, merged_state),
        "name":  merged_name,
        "city":  new_track.get("city") or existing_track.get("city"),
        "state": merged_state,
    }

    # Dates — new flyer wins (may have corrected or extended dates)
    if new_data.get("dates", {}).get("start"):
        merged["dates"] = new_data["dates"]

    # Times — new flyer wins for any non-null time
    existing_times = existing.get("times", {})
    new_times = new_data.get("times", {})
    merged["times"] = {
        "gates_open": new_times.get("gates_open") or existing_times.get("gates_open"),
        "registration_opens": new_times.get("registration_opens") or existing_times.get("registration_opens"),
        "race_start": new_times.get("race_start") or existing_times.get("race_start"),
    }

    # Fees — new flyer wins if present
    existing_fees = existing.get("fees", {})
    new_fees = new_data.get("fees", {})
    merged["fees"] = {
        "entry": new_fees.get("entry") or existing_fees.get("entry"),
        "spectator": new_fees.get("spectator") or existing_fees.get("spectator"),
    }

    # Contact — union, new wins on conflict
    existing_contact = existing.get("contact", {})
    new_contact = new_data.get("contact", {})
    merged["contact"] = {
        "phone": new_contact.get("phone") or existing_contact.get("phone"),
        "email": new_contact.get("email") or existing_contact.get("email"),
        "website": new_contact.get("website") or existing_contact.get("website"),
    }

    # Classes — union of both sets
    existing_classes = set(existing.get("classes", []))
    new_classes = set(new_data.get("classes", []))
    merged["classes"] = sorted(existing_classes | new_classes)

    # Confidence — take the higher value
    merged["confidence"] = max(existing.get("confidence", 0), new_data.get("confidence", 0))

    # Append new flyer to history
    merged["flyers"] = existing.get("flyers", []) + [new_flyer_entry]

    return merged

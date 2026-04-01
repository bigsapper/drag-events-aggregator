"""
One-time migration: translate dfw-dragevents events.json + tracks.json
into the drag-events-aggregator dist/events.json schema.

Usage:
    python migrate.py

Throwaway script — safe to delete after running.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

SRC_EVENTS = Path("../dfw-dragevents/site/data/events.json")
SRC_TRACKS = Path("../dfw-dragevents/site/data/tracks.json")
DEST        = Path("dist/events.json")

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_state(address: str) -> str | None:
    """Extract two-letter state abbreviation from a US address string."""
    match = re.search(r'\b([A-Z]{2})\s+\d{5}', address)
    return match.group(1) if match else None


def parse_date(dt_str: str | None) -> str | None:
    """Extract YYYY-MM-DD from an ISO datetime string."""
    if not dt_str:
        return None
    return dt_str[:10]


def parse_time(dt_str: str | None) -> str | None:
    """Extract HH:MM from an ISO datetime string. Returns None if time is 00:00."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.hour == 0 and dt.minute == 0:
            return None
        return dt.strftime("%H:%M")
    except ValueError:
        return None


def format_fee(amount: float | None) -> str | None:
    if amount is None:
        return None
    return f"${int(amount)}" if amount == int(amount) else f"${amount}"


def infer_event_type(title: str, description: str) -> str:
    combined = (title + " " + (description or "")).lower()
    if "test" in combined and "tune" in combined:
        return "test_n_tune"
    if "bracket" in combined:
        return "bracket"
    if "points" in combined:
        return "points_race"
    if "no prep" in combined or "no-prep" in combined:
        return "no_prep"
    if "grudge" in combined:
        return "grudge"
    if "nhra" in combined or "ihra" in combined or "national" in combined:
        return "points_race"
    return "unknown"


# ── Main ──────────────────────────────────────────────────────────────────────

tracks_raw = json.loads(SRC_TRACKS.read_text())
track_map  = {t["id"]: t for t in tracks_raw}

events_raw = json.loads(SRC_EVENTS.read_text())

now = datetime.now(timezone.utc).isoformat()
output = []

for src in events_raw:
    track_rec = track_map.get(src["track_id"], {})
    address   = track_rec.get("address", "")
    state     = parse_state(address)

    # Deduplicate class names (source data has duplicates in some records)
    class_names = list(dict.fromkeys(c["name"] for c in src.get("classes", [])))

    event = {
        "id":         str(uuid.uuid4()),
        "title":      src["title"],
        "event_type": infer_event_type(src["title"], src.get("description", "")),
        "series":     None,
        "track": {
            "name":  src["track_name"],
            "city":  track_rec.get("city"),
            "state": state,
        },
        "dates": {
            "start": parse_date(src.get("start_date")),
            "end":   parse_date(src.get("end_date")),
        },
        "times": {
            "gates_open":         None,
            "registration_opens": None,
            "race_start":         parse_time(src.get("start_date")),
        },
        "classes":        class_names,
        "fees": {
            "entry":     format_fee(src.get("event_driver_fee")),
            "spectator": format_fee(src.get("event_spectator_fee")),
        },
        "contact": {
            "phone":   None,
            "email":   None,
            "website": src.get("url") or track_rec.get("url"),
        },
        "confidence":     1.0,
        "unclear_fields": [],
        "notes":          src.get("description") or None,
        "flyers":         [],
        "created_at":     now,
        "updated_at":     now,
    }
    output.append(event)

DEST.write_text(json.dumps(output, indent=2))
print(f"Migrated {len(output)} events → {DEST}")

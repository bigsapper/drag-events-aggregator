"""Process drag racing event flyers and store results in events.json.

Usage:
    # Process a single flyer
    python -m drag_events.process path/to/flyer.jpg

    # Process all images in a directory
    python -m drag_events.process path/to/flyers/

    # Process multiple specific files
    python -m drag_events.process flyer1.jpg flyer2.png flyer3.jpg
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .dedup import (
    compute_phash, is_duplicate_image, find_same_event, merge_events, track_slug,
    backfill_track_from_catalog, backfill_contact_from_catalog,
)
from .event_filters import is_in_scope_event, is_past_event
from .extract import extract_event
from .logging_utils import get_logger
from .validate_events import validate_events_payload

LOGGER = get_logger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
EVENTS_FILE = BASE_DIR / "dist" / "events.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _normalize_contact_website(event: dict) -> dict:
    contact = event.get("contact")
    if not isinstance(contact, dict):
        return event

    website = contact.get("website")
    if not isinstance(website, str) or not website.strip():
        return event

    normalized = website.strip()
    parsed = urlparse(normalized)
    if not parsed.scheme and "." in normalized:
        normalized = f"https://{normalized}"

    contact["website"] = normalized
    return event


def load_events() -> list[dict]:
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text())
    return []


def save_events(events: list[dict]) -> None:
    validate_events_payload(events)
    EVENTS_FILE.write_text(json.dumps(events, indent=2))


def process_flyer(image_path: str, events: list[dict]) -> tuple[str, dict]:
    """Process one flyer. Returns (outcome, event) where outcome is one of:
      'new'       — new event added
      'merged'    — updated existing event with new flyer details
      'duplicate' — exact image already processed, skipped
      'skipped'   — extracted but filtered out as out-of-scope or past-dated
    """
    path = Path(image_path)
    LOGGER.info("  Computing image hash...")
    phash = compute_phash(image_path)

    # Layer 1: exact/near-duplicate image check
    existing = is_duplicate_image(phash, events)
    if existing:
        LOGGER.info(f"  Duplicate image detected (matches event: {existing.get('title', existing['id'])}), skipping API call.")
        return "duplicate", existing

    # Layer 2: call Claude to extract event data
    LOGGER.info("  Calling Claude vision API...")
    extracted = extract_event(image_path)
    extracted = _normalize_contact_website(extracted)

    if not is_in_scope_event(extracted):
        LOGGER.info("  Out-of-scope event detected, skipping.")
        return "skipped", extracted

    if is_past_event(extracted):
        LOGGER.info("  Past event detected, skipping.")
        return "skipped", extracted

    flyer_entry = {
        "file": path.name,
        "phash": phash,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }

    # Layer 3: same event, different flyer (reminder/update flyer)
    same_event = find_same_event(extracted, events)
    if same_event:
        LOGGER.info(f"  Same event detected ('{same_event.get('title', same_event['id'])}'), merging...")
        merged = merge_events(same_event, extracted, flyer_entry)
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Replace in list
        idx = next(i for i, e in enumerate(events) if e["id"] == same_event["id"])
        events[idx] = merged
        return "merged", merged

    # New event
    track = extracted.get("track") or {}
    track_with_id = {
        "id":    track_slug(track.get("name"), track.get("state")),
        "name":  track.get("name"),
        "city":  track.get("city"),
        "state": track.get("state"),
    }
    extracted["track"] = backfill_track_from_catalog(track_with_id)
    if extracted.get("contact") is not None:
        extracted["contact"] = backfill_contact_from_catalog(
            extracted["track"]["id"], extracted["contact"]
        )
    new_event = {
        "id": str(uuid.uuid4()),
        **extracted,
        "flyers": [flyer_entry],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    events.append(new_event)
    return "new", new_event


def collect_images(paths: list[str]) -> list[Path]:
    images = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for ext in IMAGE_EXTENSIONS:
                images.extend(path.glob(f"*{ext}"))
                images.extend(path.glob(f"*{ext.upper()}"))
        elif path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
        else:
            LOGGER.warning(f"  Skipping {p} (not a supported image type)")
    return sorted(set(images))


def main():
    if len(sys.argv) < 2:
        LOGGER.info(__doc__.rstrip())
        sys.exit(1)

    images = collect_images(sys.argv[1:])
    if not images:
        LOGGER.info("No images found.")
        sys.exit(1)

    events = load_events()
    LOGGER.info(f"Loaded {len(events)} existing events.\n")

    counts = {"new": 0, "merged": 0, "duplicate": 0, "skipped": 0, "error": 0}

    for image_path in images:
        LOGGER.info(f"Processing: {image_path.name}")
        try:
            outcome, event = process_flyer(str(image_path), events)
            counts[outcome] += 1
            label = {"new": "NEW", "merged": "UPDATED", "duplicate": "SKIPPED", "skipped": "SKIPPED"}[outcome]
            title = event.get("title", event.get("id", "?"))
            date_start = event.get("dates", {}).get("start", "?")
            track = event.get("track", {}).get("name", "?")
            LOGGER.info(f"  [{label}] {title} — {track} — {date_start}")
            if "test-flyers" not in image_path.parts:
                image_path.unlink()
        except Exception as e:
            LOGGER.error(f"  [ERROR] {e}")
            counts["error"] += 1
        LOGGER.info("")

    save_events(events)

    LOGGER.info("─" * 50)
    LOGGER.info(f"Done. {len(events)} total events in database.")
    LOGGER.info(
        f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  "
        f"{counts['skipped']} skipped  |  {counts['error']} errors"
    )


if __name__ == "__main__":
    main()

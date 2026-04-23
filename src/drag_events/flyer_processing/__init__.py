"""Process drag racing flyer images and store results in events.json.

Usage:
    # Process a single flyer
    python -m drag_events.flyer_processing path/to/flyer.jpg

    # Process all images in a directory
    python -m drag_events.flyer_processing path/to/flyers/

    # Process multiple specific files
    python -m drag_events.flyer_processing flyer1.jpg flyer2.png flyer3.jpg
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ..events.dedup import (
    backfill_contact_from_catalog,
    backfill_track_from_catalog,
    compute_phash,
    find_same_event,
    is_duplicate_image,
    merge_events,
    track_slug,
)
from ..events.filters import is_in_scope_event, is_past_event
from ..event_validation import validate_events_payload
from ..core.logging_utils import get_logger
from ..core.paths import EVENTS_FILE
from ..extraction.image import extract_event

LOGGER = get_logger(__name__)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
OUTCOME_LABELS = {
    "new": "NEW",
    "merged": "UPDATED",
    "duplicate": "SKIPPED",
    "skipped": "SKIPPED",
}


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


def _replace_event(events: list[dict], event_id: str, updated_event: dict) -> None:
    idx = next(i for i, event in enumerate(events) if event["id"] == event_id)
    events[idx] = updated_event


def _build_track_with_id(extracted: dict) -> dict:
    track = extracted.get("track") or {}
    return {
        "id": track_slug(track.get("name"), track.get("state")),
        "name": track.get("name"),
        "city": track.get("city"),
        "state": track.get("state"),
    }


def _build_flyer_entry(path: Path, phash: str, processed_at: str) -> dict:
    return {
        "file": path.name,
        "phash": phash,
        "processed_at": processed_at,
    }


def _extract_and_filter_event(image_path: str) -> tuple[dict | None, tuple[str, dict] | None]:
    LOGGER.info("  Calling Claude vision API...")
    extracted = extract_event(image_path)
    extracted = _normalize_contact_website(extracted)

    if not is_in_scope_event(extracted):
        LOGGER.info("  Out-of-scope event detected, skipping.")
        return None, ("skipped", extracted)

    if is_past_event(extracted):
        LOGGER.info("  Past event detected, skipping.")
        return None, ("skipped", extracted)

    return extracted, None


def _merge_existing_event(events: list[dict], same_event: dict, extracted: dict, flyer_entry: dict, processed_at: str) -> dict:
    LOGGER.info(f"  Same event detected ('{same_event.get('title', same_event['id'])}'), merging...")
    merged = merge_events(same_event, extracted, flyer_entry)
    merged["updated_at"] = processed_at
    _replace_event(events, same_event["id"], merged)
    return merged


def _build_new_event(extracted: dict, flyer_entry: dict, processed_at: str) -> dict:
    extracted["track"] = backfill_track_from_catalog(_build_track_with_id(extracted))
    if extracted.get("contact") is not None:
        extracted["contact"] = backfill_contact_from_catalog(
            extracted["track"]["id"], extracted["contact"]
        )
    return {
        "id": str(uuid.uuid4()),
        **extracted,
        "flyers": [flyer_entry],
        "created_at": processed_at,
        "updated_at": processed_at,
    }


def process_flyer(image_path: str, events: list[dict]) -> tuple[str, dict]:
    """Process one flyer. Returns (outcome, event)."""
    path = Path(image_path)
    LOGGER.info("  Computing image hash...")
    phash = compute_phash(image_path)

    existing = is_duplicate_image(phash, events)
    if existing:
        LOGGER.info(f"  Duplicate image detected (matches event: {existing.get('title', existing['id'])}), skipping API call.")
        return "duplicate", existing

    extracted, filtered = _extract_and_filter_event(image_path)
    if filtered is not None:
        return filtered

    processed_at = datetime.now(timezone.utc).isoformat()
    flyer_entry = _build_flyer_entry(path, phash, processed_at)

    same_event = find_same_event(extracted, events)
    if same_event:
        merged = _merge_existing_event(events, same_event, extracted, flyer_entry, processed_at)
        return "merged", merged

    new_event = _build_new_event(extracted, flyer_entry, processed_at)
    events.append(new_event)
    return "new", new_event


def collect_images(paths: list[str]) -> list[Path]:
    images = []
    for candidate in paths:
        path = Path(candidate)
        if path.is_dir():
            for ext in IMAGE_EXTENSIONS:
                images.extend(path.glob(f"*{ext}"))
                images.extend(path.glob(f"*{ext.upper()}"))
        elif path.suffix.lower() in IMAGE_EXTENSIONS:
            images.append(path)
        else:
            LOGGER.warning(f"  Skipping {candidate} (not a supported image type)")
    return sorted(set(images))


def main() -> None:
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
            label = OUTCOME_LABELS[outcome]
            title = event.get("title", event.get("id", "?"))
            date_start = event.get("dates", {}).get("start", "?")
            track = event.get("track", {}).get("name", "?")
            LOGGER.info(f"  [{label}] {title} - {track} - {date_start}")
            if "test-flyers" not in image_path.parts:
                image_path.unlink()
        except Exception as exc:
            LOGGER.error(f"  [ERROR] {exc}")
            counts["error"] += 1
        LOGGER.info("")

    save_events(events)

    LOGGER.info("-" * 50)
    LOGGER.info(f"Done. {len(events)} total events in database.")
    LOGGER.info(
        f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  "
        f"{counts['skipped']} skipped  |  {counts['error']} errors"
    )

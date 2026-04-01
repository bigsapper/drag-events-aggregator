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

from dotenv import load_dotenv

from .dedup import compute_phash, is_duplicate_image, find_same_event, merge_events, track_slug
from .extract import extract_event

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
EVENTS_FILE = BASE_DIR / "dist" / "events.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def load_events() -> list[dict]:
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text())
    return []


def save_events(events: list[dict]) -> None:
    EVENTS_FILE.write_text(json.dumps(events, indent=2))


def process_flyer(image_path: str, events: list[dict]) -> tuple[str, dict]:
    """Process one flyer. Returns (outcome, event) where outcome is one of:
      'new'       — new event added
      'merged'    — updated existing event with new flyer details
      'duplicate' — exact image already processed, skipped
    """
    path = Path(image_path)
    print(f"  Computing image hash...")
    phash = compute_phash(image_path)

    # Layer 1: exact/near-duplicate image check
    existing = is_duplicate_image(phash, events)
    if existing:
        print(f"  Duplicate image detected (matches event: {existing.get('title', existing['id'])}), skipping API call.")
        return "duplicate", existing

    # Layer 2: call Claude to extract event data
    print(f"  Calling Claude vision API...")
    extracted = extract_event(image_path)

    flyer_entry = {
        "file": path.name,
        "phash": phash,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }

    # Layer 3: same event, different flyer (reminder/update flyer)
    same_event = find_same_event(extracted, events)
    if same_event:
        print(f"  Same event detected ('{same_event.get('title', same_event['id'])}'), merging...")
        merged = merge_events(same_event, extracted, flyer_entry)
        merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        # Replace in list
        idx = next(i for i, e in enumerate(events) if e["id"] == same_event["id"])
        events[idx] = merged
        return "merged", merged

    # New event
    track = extracted.get("track") or {}
    extracted["track"] = {
        "id":    track_slug(track.get("name"), track.get("state")),
        "name":  track.get("name"),
        "city":  track.get("city"),
        "state": track.get("state"),
    }
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
            print(f"  Skipping {p} (not a supported image type)")
    return sorted(set(images))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    images = collect_images(sys.argv[1:])
    if not images:
        print("No images found.")
        sys.exit(1)

    events = load_events()
    print(f"Loaded {len(events)} existing events.\n")

    counts = {"new": 0, "merged": 0, "duplicate": 0, "error": 0}

    for image_path in images:
        print(f"Processing: {image_path.name}")
        try:
            outcome, event = process_flyer(str(image_path), events)
            counts[outcome] += 1
            label = {"new": "NEW", "merged": "UPDATED", "duplicate": "SKIPPED"}[outcome]
            title = event.get("title", event.get("id", "?"))
            date_start = event.get("dates", {}).get("start", "?")
            track = event.get("track", {}).get("name", "?")
            print(f"  [{label}] {title} — {track} — {date_start}")
            if "test-flyers" not in image_path.parts:
                image_path.unlink()
        except Exception as e:
            print(f"  [ERROR] {e}")
            counts["error"] += 1
        print()

    save_events(events)

    print("─" * 50)
    print(f"Done. {len(events)} total events in database.")
    print(f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  {counts['error']} errors")


if __name__ == "__main__":
    main()

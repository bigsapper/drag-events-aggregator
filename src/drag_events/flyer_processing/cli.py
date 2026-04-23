"""Process drag racing flyer images and store results in events.json.

Usage:
    # Process a single flyer
    python -m drag_events.flyer_processing path/to/flyer.jpg

    # Process all images in a directory
    python -m drag_events.flyer_processing path/to/flyers/

    # Process multiple specific files
    python -m drag_events.flyer_processing flyer1.jpg flyer2.png flyer3.jpg
"""

import sys

from .pipeline import (
    LOGGER,
    OUTCOME_LABELS,
    collect_images,
    load_events,
    process_flyer,
    save_events,
)


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

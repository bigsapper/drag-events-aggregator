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

from .pipeline import LOGGER, run_pipeline


def main() -> None:
    if len(sys.argv) < 2:
        LOGGER.info(__doc__.rstrip())
        sys.exit(1)
    counts = run_pipeline(sys.argv[1:])
    if not any(counts.values()):
        LOGGER.info("No images found.")
        sys.exit(1)

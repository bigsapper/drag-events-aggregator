"""Full pipeline orchestrator: sync flyers, crawl, process staged images, validate."""

import sys

from .core.logging_utils import get_logger
from .core.paths import FLYERS_DIR
from .crawl import cli as crawl_cli
from .event_validation.cli import SchemaValidationError, validate_events_file
from .flyer_processing.pipeline import run_pipeline
from .flyer_sync.cli import run_cli as run_flyer_sync

LOGGER = get_logger(__name__)


def main() -> None:
    LOGGER.info("=== Step 1: Sync flyers from Google Drive ===")
    run_flyer_sync()

    LOGGER.info("\n=== Step 2: Crawl tracks and aggregators ===")
    crawl_cli.main()

    LOGGER.info("\n=== Step 3: Process staged flyer images ===")
    counts = run_pipeline([str(FLYERS_DIR)])
    if not any(counts.values()):
        LOGGER.info("No staged flyer images to process.")

    LOGGER.info("\n=== Step 4: Validate events output ===")
    try:
        validate_events_file()
        LOGGER.info("Validation passed.")
    except SchemaValidationError as exc:
        LOGGER.error(f"Validation failed:\n{exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

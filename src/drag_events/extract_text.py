"""Convert text-based event listings (RacingJunk, MyRacePass) into structured event records."""

import time
from datetime import date

from .retry_utils import execute_with_retries
from .secrets import get_anthropic_client
from .schema import EVENT_INPUT_SCHEMA
from .validate_events import validate_payload_against_schema

TOOL = {
    "name": "store_event",
    "description": "Store structured drag racing event data parsed from a text listing.",
    "input_schema": EVENT_INPUT_SCHEMA,
}

CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_BASE_DELAY_SECONDS = 1.0


def _date_inference_instruction(today: date | None = None) -> str:
    current_date = today or date.today()
    return (
        f"Today's date is {current_date.isoformat()}. "
        f"If the listing omits the year, default to {current_date.year} unless the listing clearly indicates a different year."
    )


def extract_from_text(listing: dict) -> dict:
    """Parse a text event listing into structured event data via Claude."""
    text = "\n".join(f"{k}: {v}" for k, v in listing.items() if v and k != "source")

    response = execute_with_retries(
        lambda: get_anthropic_client().messages.create(
            model="claude-haiku-4-5-20251001",  # text-only; haiku is sufficient and cheaper
            max_tokens=512,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "store_event"},
            messages=[{
                "role": "user",
                "content": (
                    "Parse this drag racing event listing into structured data. "
                    "Infer event_type from the title if not explicit. "
                    "Convert dates to YYYY-MM-DD. Extract city/state from location text. "
                    "Always include confidence as a number between 0 and 1. "
                    + _date_inference_instruction()
                    + "\n\n"
                    + text
                )
            }],
        ),
        category="claude",
        max_attempts=CLAUDE_MAX_ATTEMPTS,
        base_delay_seconds=CLAUDE_RETRY_BASE_DELAY_SECONDS,
        sleep=time.sleep,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "store_event":
            validate_payload_against_schema(block.input, EVENT_INPUT_SCHEMA)
            return block.input

    raise ValueError(f"Claude did not call store_event for listing: {listing.get('title')}")

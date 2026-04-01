"""Convert text-based event listings (RacingJunk, MyRacePass) into structured event records."""

import os
import time

import anthropic
from dotenv import load_dotenv

from .retry_utils import execute_with_retries
from .schema import EVENT_INPUT_SCHEMA

load_dotenv()

CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TOOL = {
    "name": "store_event",
    "description": "Store structured drag racing event data parsed from a text listing.",
    "input_schema": EVENT_INPUT_SCHEMA,
}

CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_BASE_DELAY_SECONDS = 1.0


def extract_from_text(listing: dict) -> dict:
    """Parse a text event listing into structured event data via Claude."""
    text = "\n".join(f"{k}: {v}" for k, v in listing.items() if v and k != "source")

    response = execute_with_retries(
        lambda: CLIENT.messages.create(
            model="claude-haiku-4-5-20251001",  # text-only; haiku is sufficient and cheaper
            max_tokens=512,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "store_event"},
            messages=[{
                "role": "user",
                "content": (
                    "Parse this drag racing event listing into structured data. "
                    "Infer event_type from the title if not explicit. "
                    "Convert dates to YYYY-MM-DD. Extract city/state from location text.\n\n"
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
            return block.input

    raise ValueError(f"Claude did not call store_event for listing: {listing.get('title')}")

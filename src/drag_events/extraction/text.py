"""Convert text-based event listings (RacingJunk, MyRacePass) into structured event records."""

import time

from ..core.secrets import get_anthropic_client
from .common import (
    build_date_inference_instruction,
    build_store_event_tool,
    request_structured_event,
)

TOOL = build_store_event_tool("Store structured drag racing event data parsed from a text listing.")


def _date_inference_instruction(today=None) -> str:
    return build_date_inference_instruction("the listing", today)


def extract_from_text(listing: dict) -> dict:
    """Parse a text event listing into structured event data via Claude."""
    text = "\n".join(f"{k}: {v}" for k, v in listing.items() if v and k != "source")

    try:
        return request_structured_event(
            model="claude-haiku-4-5-20251001",  # text-only; haiku is sufficient and cheaper
            max_tokens=512,
            tool=TOOL,
            get_client=get_anthropic_client,
            sleep=time.sleep,
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
        )
    except ValueError as exc:
        if "store_event" in str(exc):
            raise ValueError(f"Claude did not call store_event for listing: {listing.get('title')}") from exc
        raise

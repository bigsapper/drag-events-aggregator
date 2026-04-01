"""Claude vision extraction for drag racing event flyers."""

import base64
import time
from pathlib import Path

from .retry_utils import execute_with_retries
from .secrets import get_anthropic_client
from .schema import EVENT_INPUT_SCHEMA

TOOL = {
    "name": "store_event",
    "description": "Store structured drag racing event data extracted from a flyer image.",
    "input_schema": EVENT_INPUT_SCHEMA,
}

SYSTEM_PROMPT = """You are an expert at reading drag racing event flyers. Extract all event information accurately.

Drag racing knowledge:
- Common event types: bracket racing, points races, test & tune, no-prep, grudge racing
- Common classes: Top Fuel, Funny Car, Pro Stock, Pro Mod, Top Sportsman, Top Dragster, Super Pro, Pro, Sportsman, Street, Jr Dragster, index classes (5.0, 5.90, 7.90, etc.)
- Tracks often list gates open time, registration time, and first round time separately
- Entry fees may be per class or per car; note exactly as written
- Dates on flyers are often stylized - convert to YYYY-MM-DD format
- If the year is not shown, infer from context (upcoming events)
- State abbreviations are standard US postal codes

Set confidence based on image clarity and completeness of information visible."""

CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_BASE_DELAY_SECONDS = 1.0


def extract_event(image_path: str) -> dict:
    """Send a flyer image to Claude and return extracted event data."""
    path = Path(image_path)
    image_bytes = path.read_bytes()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    suffix = path.suffix.lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_type_map.get(suffix, "image/jpeg")

    response = execute_with_retries(
        lambda: get_anthropic_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "store_event"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": b64}
                        },
                        {
                            "type": "text",
                            "text": "Extract all drag racing event information from this flyer."
                        }
                    ]
                }
            ],
        ),
        category="claude",
        max_attempts=CLAUDE_MAX_ATTEMPTS,
        base_delay_seconds=CLAUDE_RETRY_BASE_DELAY_SECONDS,
        sleep=time.sleep,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "store_event":
            return block.input

    raise ValueError(f"Claude did not call store_event tool for {image_path}")

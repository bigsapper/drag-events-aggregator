"""Claude vision extraction for drag racing event flyers."""

import base64
import time
from pathlib import Path

from .extraction_common import (
    build_date_inference_instruction,
    build_store_event_tool,
    request_structured_event,
)
from .secrets import get_anthropic_client

SYSTEM_PROMPT = """You are an expert at reading drag racing event flyers. Extract all event information accurately.

Drag racing knowledge:
- Common event types: bracket racing, points races, test & tune, no-prep, grudge racing
- Common classes: Top Fuel, Funny Car, Pro Stock, Pro Mod, Top Sportsman, Top Dragster, Super Pro, Pro, Sportsman, Street, Jr Dragster, index classes (5.0, 5.90, 7.90, etc.)
- Tracks often list gates open time, registration time, and first round time separately
- Entry fees may be per class or per car; note exactly as written
- Dates on flyers are often stylized - convert to YYYY-MM-DD format
- If the year is not shown, infer from context (upcoming events)
- State abbreviations are standard US postal codes

Set confidence based on image clarity and completeness of information visible.
Always include the confidence field as a number between 0 and 1."""

TOOL = build_store_event_tool("Store structured drag racing event data extracted from a flyer image.")


def _date_inference_instruction(today=None) -> str:
    return build_date_inference_instruction("a flyer", today)


def _media_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    return media_type_map.get(suffix, "image/jpeg")

def extract_event(image_path: str) -> dict:
    """Send a flyer image to Claude and return extracted event data."""
    path = Path(image_path)
    image_bytes = path.read_bytes()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    media_type = _media_type_for_path(path)

    return request_structured_event(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tool=TOOL,
        get_client=get_anthropic_client,
        sleep=time.sleep,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all drag racing event information from this flyer. "
                            + _date_inference_instruction()
                        ),
                    },
                ],
            }
        ],
    )

"""Claude vision extraction for drag racing event flyers."""

import anthropic
import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TOOL = {
    "name": "store_event",
    "description": "Store structured drag racing event data extracted from a flyer image.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Full event name/title as shown on the flyer"
            },
            "event_type": {
                "type": "string",
                "enum": ["bracket", "points_race", "test_n_tune", "no_prep", "grudge", "specialty", "test_day", "unknown"],
                "description": "Primary type of drag racing event"
            },
            "series": {
                "type": ["string", "null"],
                "description": "Sanctioning body or series (e.g. NHRA, IHRA, local bracket series name)"
            },
            "track": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "city": {"type": ["string", "null"]},
                    "state": {"type": ["string", "null"]}
                },
                "required": ["name"]
            },
            "dates": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "YYYY-MM-DD"},
                    "end": {"type": ["string", "null"], "description": "YYYY-MM-DD, only if multi-day"}
                },
                "required": ["start"]
            },
            "times": {
                "type": "object",
                "properties": {
                    "gates_open": {"type": ["string", "null"], "description": "HH:MM 24h"},
                    "registration_opens": {"type": ["string", "null"], "description": "HH:MM 24h"},
                    "race_start": {"type": ["string", "null"], "description": "HH:MM 24h"}
                }
            },
            "classes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of racing classes/categories on the flyer"
            },
            "fees": {
                "type": "object",
                "properties": {
                    "entry": {"type": ["string", "null"], "description": "Entry fee as written on flyer"},
                    "spectator": {"type": ["string", "null"]}
                }
            },
            "contact": {
                "type": "object",
                "properties": {
                    "phone": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "website": {"type": ["string", "null"]}
                }
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Overall confidence in the extraction (0.0-1.0)"
            },
            "unclear_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Field names where the value was unclear or uncertain"
            },
            "notes": {
                "type": ["string", "null"],
                "description": "Any additional information on the flyer not captured by other fields"
            }
        },
        "required": ["title", "event_type", "track", "dates", "confidence"]
    }
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


def extract_event(image_path: str) -> dict:
    """Send a flyer image to Claude and return extracted event data."""
    path = Path(image_path)
    image_bytes = path.read_bytes()
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    suffix = path.suffix.lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_type_map.get(suffix, "image/jpeg")

    response = CLIENT.messages.create(
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
        ]
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "store_event":
            return block.input

    raise ValueError(f"Claude did not call store_event tool for {image_path}")

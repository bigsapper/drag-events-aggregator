"""Convert text-based event listings (RacingJunk, MyRacePass) into structured event records."""

import os
from dotenv import load_dotenv
load_dotenv()

import anthropic

CLIENT = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TOOL = {
    "name": "store_event",
    "description": "Store structured drag racing event data parsed from a text listing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title":      {"type": "string"},
            "event_type": {"type": "string", "enum": ["bracket", "points_race", "test_n_tune", "no_prep", "grudge", "specialty", "test_day", "unknown"]},
            "series":     {"type": ["string", "null"]},
            "track": {
                "type": "object",
                "properties": {
                    "name":  {"type": "string"},
                    "city":  {"type": ["string", "null"]},
                    "state": {"type": ["string", "null"]}
                },
                "required": ["name"]
            },
            "dates": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "YYYY-MM-DD"},
                    "end":   {"type": ["string", "null"], "description": "YYYY-MM-DD"}
                },
                "required": ["start"]
            },
            "times": {
                "type": "object",
                "properties": {
                    "gates_open":          {"type": ["string", "null"]},
                    "registration_opens":  {"type": ["string", "null"]},
                    "race_start":          {"type": ["string", "null"]}
                }
            },
            "classes":  {"type": "array", "items": {"type": "string"}},
            "fees": {
                "type": "object",
                "properties": {
                    "entry":     {"type": ["string", "null"]},
                    "spectator": {"type": ["string", "null"]}
                }
            },
            "contact": {
                "type": "object",
                "properties": {
                    "phone":   {"type": ["string", "null"]},
                    "email":   {"type": ["string", "null"]},
                    "website": {"type": ["string", "null"]}
                }
            },
            "confidence":     {"type": "number", "minimum": 0, "maximum": 1},
            "unclear_fields": {"type": "array", "items": {"type": "string"}},
            "notes":          {"type": ["string", "null"]}
        },
        "required": ["title", "event_type", "track", "dates", "confidence"]
    }
}


def extract_from_text(listing: dict) -> dict:
    """Parse a text event listing into structured event data via Claude."""
    text = "\n".join(f"{k}: {v}" for k, v in listing.items() if v and k != "source")

    response = CLIENT.messages.create(
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
        }]
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "store_event":
            return block.input

    raise ValueError(f"Claude did not call store_event for listing: {listing.get('title')}")

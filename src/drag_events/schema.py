"""Shared JSON schema for the store_event Claude tool."""

EVENT_INPUT_SCHEMA = {
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

"""Shared Claude extraction helpers for image and text event parsing."""

import time
from datetime import date

from .retry_utils import execute_with_retries
from .secrets import get_anthropic_client
from .schema import EVENT_INPUT_SCHEMA
from .event_validation import validate_payload_against_schema

TOOL_NAME = "store_event"
CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_BASE_DELAY_SECONDS = 1.0


def build_store_event_tool(description: str) -> dict:
    return {
        "name": TOOL_NAME,
        "description": description,
        "input_schema": EVENT_INPUT_SCHEMA,
    }


def build_date_inference_instruction(subject_noun: str, today: date | None = None) -> str:
    current_date = today or date.today()
    return (
        f"Today's date is {current_date.isoformat()}. "
        f"If {subject_noun} omits the year, default to {current_date.year} unless {subject_noun} clearly indicates a different year."
    )


def request_structured_event(
    *,
    model: str,
    max_tokens: int,
    tool: dict,
    get_client,
    sleep=time.sleep,
    messages: list[dict],
    system: str | None = None,
) -> dict:
    request_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": TOOL_NAME},
        "messages": messages,
    }
    if system is not None:
        request_kwargs["system"] = system

    response = execute_with_retries(
        lambda: get_client().messages.create(**request_kwargs),
        category="claude",
        max_attempts=CLAUDE_MAX_ATTEMPTS,
        base_delay_seconds=CLAUDE_RETRY_BASE_DELAY_SECONDS,
        sleep=sleep,
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == TOOL_NAME:
            validate_payload_against_schema(block.input, EVENT_INPUT_SCHEMA)
            return block.input

    raise ValueError(f"Claude did not call {TOOL_NAME}")

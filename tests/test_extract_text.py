"""Tests for extract_text.py — Claude text extraction."""

from datetime import date

import pytest
from unittest.mock import MagicMock, patch

from drag_events import extract_text


SAMPLE_LISTING = {
    "title": "Summer Bracket Bash",
    "date_text": "June 14, 2026",
    "location_text": "Tulsa, OK",
    "source_url": "https://racingjunk.com/event/123",
    "source": "RacingJunk",
}


def test_extract_from_text_returns_dict(mock_text_client, sample_extracted):
    result = extract_text.extract_from_text(SAMPLE_LISTING)
    assert isinstance(result, dict)
    assert result["title"] == sample_extracted["title"]


def test_extract_from_text_calls_messages_create(mock_text_client):
    extract_text.extract_from_text(SAMPLE_LISTING)
    assert mock_text_client.call_count == 1


def test_extract_from_text_uses_haiku_model(mock_text_client):
    extract_text.extract_from_text(SAMPLE_LISTING)
    call_kwargs = mock_text_client.call_args[1]
    assert "haiku" in call_kwargs["model"]


def test_extract_from_text_excludes_source_key(mock_text_client):
    """'source' key should not appear in the text sent to Claude."""
    extract_text.extract_from_text(SAMPLE_LISTING)
    call_kwargs = mock_text_client.call_args[1]
    content = call_kwargs["messages"][0]["content"]
    assert "source: RacingJunk" not in content


def test_extract_from_text_includes_title_in_prompt(mock_text_client):
    extract_text.extract_from_text(SAMPLE_LISTING)
    call_kwargs = mock_text_client.call_args[1]
    content = call_kwargs["messages"][0]["content"]
    assert "Summer Bracket Bash" in content


def test_extract_from_text_includes_current_year_default_instruction(mock_text_client):
    with patch("drag_events.extract_text._date_inference_instruction", return_value="Today's date is 2026-04-06. If the listing omits the year, default to 2026 unless the listing clearly indicates a different year."):
        extract_text.extract_from_text(SAMPLE_LISTING)
    call_kwargs = mock_text_client.call_args[1]
    content = call_kwargs["messages"][0]["content"]
    assert "default to 2026" in content


def test_text_date_inference_instruction_uses_supplied_date():
    text = extract_text._date_inference_instruction(date(2026, 4, 6))
    assert "Today's date is 2026-04-06." in text
    assert "default to 2026" in text


def test_extract_from_text_raises_if_no_tool_call():
    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]
    client = MagicMock()
    client.messages.create.return_value = mock_response
    with patch("drag_events.extract_text.get_anthropic_client", return_value=client):
        with pytest.raises(ValueError, match="store_event"):
            extract_text.extract_from_text(SAMPLE_LISTING)


def test_extract_from_text_rejects_missing_confidence(sample_extracted):
    invalid = dict(sample_extracted)
    invalid.pop("confidence")
    response = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.name = "store_event"
    block.input = invalid
    response.content = [block]

    client = MagicMock()
    client.messages.create.return_value = response
    with patch("drag_events.extract_text.get_anthropic_client", return_value=client):
        with pytest.raises(ValueError, match="confidence"):
            extract_text.extract_from_text(SAMPLE_LISTING)


def test_extract_from_text_retries_transient_claude_failure(sample_extracted):
    response = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.name = "store_event"
    block.input = sample_extracted
    response.content = [block]

    client = MagicMock()
    with patch("drag_events.extract_text.get_anthropic_client", return_value=client), \
         patch.object(client.messages, "create", side_effect=[RuntimeError("timeout"), response]) as mock_create, \
         patch("drag_events.extract_text.time.sleep") as mock_sleep:
        result = extract_text.extract_from_text(SAMPLE_LISTING)

    assert result["title"] == sample_extracted["title"]
    assert mock_create.call_count == 2
    mock_sleep.assert_called_once_with(1.0)

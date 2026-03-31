"""Tests for extract_text.py — Claude text extraction."""

import pytest
from unittest.mock import MagicMock, patch

import extract_text


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


def test_extract_from_text_raises_if_no_tool_call():
    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]
    with patch("extract_text.CLIENT.messages.create", return_value=mock_response):
        with pytest.raises(ValueError, match="store_event"):
            extract_text.extract_from_text(SAMPLE_LISTING)

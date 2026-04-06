"""Tests for extract.py — Claude vision extraction."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from drag_events import extract
from tests.conftest import make_1x1_png


def test_extract_event_returns_dict(tmp_path, mock_vision_client, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.png")
    result = extract.extract_event(str(img))
    assert isinstance(result, dict)
    assert result["title"] == sample_extracted["title"]


def test_extract_event_calls_messages_create(tmp_path, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.png")
    extract.extract_event(str(img))
    assert mock_vision_client.call_count == 1


def test_extract_event_uses_sonnet_model(tmp_path, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.png")
    extract.extract_event(str(img))
    call_kwargs = mock_vision_client.call_args[1]
    assert "sonnet" in call_kwargs["model"]


def test_extract_event_forces_tool_use(tmp_path, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.png")
    extract.extract_event(str(img))
    call_kwargs = mock_vision_client.call_args[1]
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "store_event"}


def test_extract_event_jpeg_media_type(tmp_path, mock_vision_client):
    img = tmp_path / "flyer.jpg"
    make_1x1_png(img)  # content doesn't matter, extension does
    extract.extract_event(str(img))
    messages = mock_vision_client.call_args[1]["messages"]
    image_block = messages[0]["content"][0]
    assert image_block["source"]["media_type"] == "image/jpeg"


def test_extract_event_png_media_type(tmp_path, mock_vision_client):
    img = make_1x1_png(tmp_path / "flyer.png")
    extract.extract_event(str(img))
    messages = mock_vision_client.call_args[1]["messages"]
    image_block = messages[0]["content"][0]
    assert image_block["source"]["media_type"] == "image/png"


def test_extract_event_unknown_extension_defaults_jpeg(tmp_path, mock_vision_client):
    # .bmp is not in the media_type_map
    img = tmp_path / "flyer.bmp"
    make_1x1_png(img)
    extract.extract_event(str(img))
    messages = mock_vision_client.call_args[1]["messages"]
    image_block = messages[0]["content"][0]
    assert image_block["source"]["media_type"] == "image/jpeg"


def test_extract_event_raises_if_no_tool_call(tmp_path):
    img = make_1x1_png(tmp_path / "flyer.png")
    text_block = MagicMock()
    text_block.type = "text"
    mock_response = MagicMock()
    mock_response.content = [text_block]
    client = MagicMock()
    client.messages.create.return_value = mock_response
    with patch("drag_events.extract.get_anthropic_client", return_value=client):
        with pytest.raises(ValueError, match="store_event"):
            extract.extract_event(str(img))


def test_extract_event_rejects_missing_confidence(tmp_path, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.png")
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
    with patch("drag_events.extract.get_anthropic_client", return_value=client):
        with pytest.raises(ValueError, match="confidence"):
            extract.extract_event(str(img))


def test_extract_event_retries_transient_claude_failure(tmp_path, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.png")
    response = MagicMock()
    block = MagicMock()
    block.type = "tool_use"
    block.name = "store_event"
    block.input = sample_extracted
    response.content = [block]

    client = MagicMock()
    with patch("drag_events.extract.get_anthropic_client", return_value=client), \
         patch.object(client.messages, "create", side_effect=[RuntimeError("timeout"), response]) as mock_create, \
         patch("drag_events.extract.time.sleep") as mock_sleep:
        result = extract.extract_event(str(img))

    assert result["title"] == sample_extracted["title"]
    assert mock_create.call_count == 2
    mock_sleep.assert_called_once_with(1.0)

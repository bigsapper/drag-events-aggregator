import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from drag_events.flyer_sync import cli as flyer_sync


FOLDER_HTML = """
<html>
  <body>
    <div class="flip-entry" id="entry-file123">
      <a href="https://drive.google.com/file/d/file123/view?usp=drive_web">
        <div class="flip-entry-title">event-one.jpg</div>
      </a>
    </div>
    <div class="flip-entry" id="entry-file456">
      <a href="https://drive.google.com/file/d/file456/view?usp=drive_web">
        <div class="flip-entry-title">notes.txt</div>
      </a>
    </div>
  </body>
</html>
"""


def test_extract_drive_folder_id_from_path():
    url = "https://drive.google.com/drive/folders/abc123_DEF?usp=drive_link"
    assert flyer_sync.extract_drive_folder_id(url) == "abc123_DEF"


def test_extract_drive_folder_id_from_query():
    url = "https://drive.google.com/open?id=abc123_DEF"
    assert flyer_sync.extract_drive_folder_id(url) == "abc123_DEF"


def test_extract_drive_folder_id_rejects_non_drive_url():
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="Google Drive URL"):
        flyer_sync.extract_drive_folder_id("https://example.com/folders/abc123")


def test_extract_drive_folder_id_rejects_unparseable_drive_url():
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="Could not determine Google Drive folder id"):
        flyer_sync.extract_drive_folder_id("https://drive.google.com/drive/my-drive")


def test_validate_sync_config_rejects_non_object():
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="must be an object"):
        flyer_sync.validate_sync_config([])


def test_validate_sync_config_rejects_missing_url():
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="DRAG_EVENTS_DRIVE_FOLDER_URL"):
        flyer_sync.validate_sync_config({})


def test_load_sync_config_env_var_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "flyer_sources.json"
    path.write_text(json.dumps({"google_drive_folder_url": ""}))
    monkeypatch.setenv("DRAG_EVENTS_DRIVE_FOLDER_URL", "https://drive.google.com/drive/folders/abc123")
    config = flyer_sync.load_sync_config(path)
    assert config["google_drive_folder_url"] == "https://drive.google.com/drive/folders/abc123"


def test_load_sync_config_env_var_takes_precedence_over_file(tmp_path, monkeypatch):
    path = tmp_path / "flyer_sources.json"
    path.write_text(json.dumps({"google_drive_folder_url": "https://drive.google.com/drive/folders/from-file"}))
    monkeypatch.setenv("DRAG_EVENTS_DRIVE_FOLDER_URL", "https://drive.google.com/drive/folders/from-env")
    config = flyer_sync.load_sync_config(path)
    assert config["google_drive_folder_url"] == "https://drive.google.com/drive/folders/from-env"


def test_load_sync_config_rejects_invalid_json(tmp_path):
    path = tmp_path / "flyer_sources.json"
    path.write_text("{not-json")
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="Invalid JSON"):
        flyer_sync.load_sync_config(path)


def test_load_sync_config_rejects_missing_file(tmp_path):
    with pytest.raises(flyer_sync.FlyerSyncConfigError, match="Missing flyer sync config"):
        flyer_sync.load_sync_config(tmp_path / "missing.json")


def test_load_sync_state_defaults_when_missing(tmp_path):
    assert flyer_sync.load_sync_state(tmp_path / "flyer_sync_state.json") == {
        "downloaded_drive_file_ids": []
    }


def test_load_sync_state_defaults_when_invalid_shape(tmp_path):
    path = tmp_path / "flyer_sync_state.json"
    path.write_text(json.dumps({"downloaded_drive_file_ids": "bad"}))
    assert flyer_sync.load_sync_state(path) == {"downloaded_drive_file_ids": []}


def test_load_sync_state_defaults_when_root_is_not_object(tmp_path):
    path = tmp_path / "flyer_sync_state.json"
    path.write_text(json.dumps(["bad"]))
    assert flyer_sync.load_sync_state(path) == {"downloaded_drive_file_ids": []}


def test_save_sync_state_roundtrip(tmp_path):
    path = tmp_path / "flyer_sync_state.json"
    state = {"downloaded_drive_file_ids": ["file123"]}
    flyer_sync.save_sync_state(state, path)
    assert flyer_sync.load_sync_state(path) == state


def test_parse_drive_folder_entries_extracts_records():
    assert flyer_sync.parse_drive_folder_entries(FOLDER_HTML) == [
        {
            "file_id": "file123",
            "title": "event-one.jpg",
            "view_url": "https://drive.google.com/file/d/file123/view?usp=drive_web",
        },
        {
            "file_id": "file456",
            "title": "notes.txt",
            "view_url": "https://drive.google.com/file/d/file456/view?usp=drive_web",
        },
    ]


def test_parse_drive_folder_entries_skips_incomplete_records():
    html = """
    <div class="flip-entry" id="entry-file123"></div>
    <div class="flip-entry"><a href="https://drive.google.com/file/d/file456/view"></a><div class="flip-entry-title">event.jpg</div></div>
    """
    assert flyer_sync.parse_drive_folder_entries(html) == []


def test_is_supported_image_filename_filters_by_extension():
    assert flyer_sync.is_supported_image_filename("event.jpg") is True
    assert flyer_sync.is_supported_image_filename("event.txt") is False


def test_build_destination_path_uses_suffix_for_collision(tmp_path):
    existing = tmp_path / "event.jpg"
    existing.write_bytes(b"old")
    assert flyer_sync.build_destination_path(tmp_path, "event.jpg", "file123") == tmp_path / "event-file123.jpg"


def test_fetch_drive_folder_entries_uses_embedded_view():
    session = MagicMock()
    response = MagicMock()
    response.text = FOLDER_HTML
    response.raise_for_status.return_value = None
    session.get.return_value = response

    entries = flyer_sync.fetch_drive_folder_entries(
        "https://drive.google.com/drive/folders/abc123?usp=drive_link",
        session=session,
    )

    assert entries[0]["file_id"] == "file123"
    session.get.assert_called_once_with(
        "https://drive.google.com/embeddedfolderview?id=abc123#list",
        timeout=30,
    )


def test_download_drive_file_writes_bytes(tmp_path):
    session = MagicMock()
    response = MagicMock()
    response.content = b"image-bytes"
    response.raise_for_status.return_value = None
    session.get.return_value = response

    destination = tmp_path / "event.jpg"
    flyer_sync.download_drive_file("file123", destination, session=session)

    assert destination.read_bytes() == b"image-bytes"
    session.get.assert_called_once_with(
        "https://drive.google.com/uc?export=download&id=file123",
        timeout=60,
    )


def test_sync_flyers_downloads_new_images_and_updates_state(tmp_path):
    config_path = tmp_path / "flyer_sources.json"
    config_path.write_text(
        json.dumps(
            {"google_drive_folder_url": "https://drive.google.com/drive/folders/abc123?usp=drive_link"}
        )
    )
    state_path = tmp_path / "flyer_sync_state.json"
    staging_dir = tmp_path / "flyers"
    session = MagicMock()

    folder_response = MagicMock()
    folder_response.text = FOLDER_HTML
    folder_response.raise_for_status.return_value = None
    file_response = MagicMock()
    file_response.content = b"image-bytes"
    file_response.raise_for_status.return_value = None
    session.get.side_effect = [folder_response, file_response]

    summary = flyer_sync.sync_flyers(
        config_path=config_path,
        state_path=state_path,
        staging_dir=staging_dir,
        session=session,
    )

    assert summary == {
        "listed": 2,
        "downloaded": 1,
        "skipped_known": 0,
        "skipped_non_image": 1,
    }
    assert (staging_dir / "event-one.jpg").read_bytes() == b"image-bytes"
    assert flyer_sync.load_sync_state(state_path) == {"downloaded_drive_file_ids": ["file123"]}


def test_sync_flyers_skips_known_drive_files(tmp_path):
    config_path = tmp_path / "flyer_sources.json"
    config_path.write_text(
        json.dumps(
            {"google_drive_folder_url": "https://drive.google.com/drive/folders/abc123?usp=drive_link"}
        )
    )
    state_path = tmp_path / "flyer_sync_state.json"
    state_path.write_text(json.dumps({"downloaded_drive_file_ids": ["file123"]}))
    session = MagicMock()
    folder_response = MagicMock()
    folder_response.text = FOLDER_HTML
    folder_response.raise_for_status.return_value = None
    session.get.return_value = folder_response

    summary = flyer_sync.sync_flyers(
        config_path=config_path,
        state_path=state_path,
        staging_dir=tmp_path / "flyers",
        session=session,
    )

    assert summary == {
        "listed": 2,
        "downloaded": 0,
        "skipped_known": 1,
        "skipped_non_image": 1,
    }
    session.get.assert_called_once()


def test_main_logs_summary(monkeypatch):
    monkeypatch.setattr(
        flyer_sync,
        "sync_flyers",
        lambda: {"downloaded": 1, "skipped_known": 2, "skipped_non_image": 3},
    )
    logger = MagicMock()
    monkeypatch.setattr(flyer_sync, "LOGGER", logger)

    flyer_sync.main()

    logger.info.assert_called_once_with(
        "Drive sync complete. 1 downloaded, 2 skipped as already synced, 3 skipped as non-image."
    )


def test_run_cli_exits_on_config_error():
    with patch("drag_events.flyer_sync.cli.main", side_effect=flyer_sync.FlyerSyncConfigError("bad config")):
        with patch("drag_events.flyer_sync.cli.LOGGER") as logger:
            with pytest.raises(SystemExit, match="1"):
                flyer_sync.run_cli()
            logger.error.assert_called_once_with("bad config")



"""Sync flyer images from a shared Google Drive folder into local staging.

Usage:
    python -m drag_events.flyer_sync
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from ..logging_utils import get_logger
from ..paths import FLYERS_DIR, FLYER_SOURCES_FILE, FLYER_SYNC_STATE_FILE

LOGGER = get_logger(__name__)
CONFIG_FILE = FLYER_SOURCES_FILE
STATE_FILE = FLYER_SYNC_STATE_FILE
STAGING_DIR = FLYERS_DIR

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
EMBEDDED_FOLDER_VIEW_URL = "https://drive.google.com/embeddedfolderview?id={folder_id}#list"
DIRECT_DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={file_id}"
GOOGLE_DRIVE_HOSTS = {"drive.google.com", "www.drive.google.com"}


class FlyerSyncConfigError(ValueError):
    """Raised when flyer sync configuration is invalid."""


def default_sync_state() -> dict:
    return {"downloaded_drive_file_ids": []}


def extract_drive_folder_id(folder_url: str) -> str:
    parsed = urlparse(folder_url)
    if parsed.netloc.lower() not in GOOGLE_DRIVE_HOSTS:
        raise FlyerSyncConfigError("flyer_sources.google_drive_folder_url must be a Google Drive URL")

    match = re.search(r"/folders/([A-Za-z0-9_-]+)", parsed.path)
    if match:
        return match.group(1)

    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return query_id[0]

    raise FlyerSyncConfigError("Could not determine Google Drive folder id from flyer_sources.google_drive_folder_url")


def validate_sync_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise FlyerSyncConfigError("flyer_sources config must be an object")

    folder_url = config.get("google_drive_folder_url")
    if not isinstance(folder_url, str) or not folder_url.strip():
        raise FlyerSyncConfigError("flyer_sources.google_drive_folder_url must be a non-empty string")

    extract_drive_folder_id(folder_url)
    return config


def load_sync_config(path: Path = CONFIG_FILE) -> dict:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise FlyerSyncConfigError(f"Missing flyer sync config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FlyerSyncConfigError(f"Invalid JSON in {path}: {exc}") from exc
    return validate_sync_config(data)


def load_sync_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return default_sync_state()
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        return default_sync_state()
    file_ids = data.get("downloaded_drive_file_ids")
    if not isinstance(file_ids, list) or not all(isinstance(item, str) for item in file_ids):
        return default_sync_state()
    return {"downloaded_drive_file_ids": file_ids}


def save_sync_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def parse_drive_folder_entries(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for entry in soup.select(".flip-entry"):
        file_id = ""
        if entry.get("id", "").startswith("entry-"):
            file_id = entry["id"][len("entry-"):]
        link = entry.select_one("a[href]")
        title = entry.select_one(".flip-entry-title")
        if not file_id or not link or not title:
            continue
        entries.append(
            {
                "file_id": file_id,
                "title": title.get_text(strip=True),
                "view_url": link["href"],
            }
        )
    return entries


def is_supported_image_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def build_destination_path(staging_dir: Path, filename: str, file_id: str) -> Path:
    candidate = staging_dir / filename
    if not candidate.exists():
        return candidate

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    return staging_dir / f"{stem}-{file_id[:8]}{suffix}"


def fetch_drive_folder_entries(folder_url: str, *, session=requests) -> list[dict]:
    folder_id = extract_drive_folder_id(folder_url)
    response = session.get(EMBEDDED_FOLDER_VIEW_URL.format(folder_id=folder_id), timeout=30)
    response.raise_for_status()
    return parse_drive_folder_entries(response.text)


def download_drive_file(file_id: str, destination: Path, *, session=requests) -> None:
    response = session.get(DIRECT_DOWNLOAD_URL.format(file_id=file_id), timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)


def sync_flyers(*, config_path: Path = CONFIG_FILE, state_path: Path = STATE_FILE, staging_dir: Path = STAGING_DIR, session=requests) -> dict:
    config = load_sync_config(config_path)
    state = load_sync_state(state_path)
    downloaded_ids = set(state["downloaded_drive_file_ids"])

    staging_dir.mkdir(parents=True, exist_ok=True)

    entries = fetch_drive_folder_entries(config["google_drive_folder_url"], session=session)
    summary = {"listed": len(entries), "downloaded": 0, "skipped_known": 0, "skipped_non_image": 0}

    for entry in entries:
        filename = entry["title"]
        file_id = entry["file_id"]

        if not is_supported_image_filename(filename):
            summary["skipped_non_image"] += 1
            continue

        if file_id in downloaded_ids:
            summary["skipped_known"] += 1
            continue

        destination = build_destination_path(staging_dir, filename, file_id)
        LOGGER.info(f"Downloading {filename}")
        download_drive_file(file_id, destination, session=session)
        downloaded_ids.add(file_id)
        summary["downloaded"] += 1

    state["downloaded_drive_file_ids"] = sorted(downloaded_ids)
    save_sync_state(state, state_path)
    return summary


def main() -> None:
    summary = sync_flyers()
    LOGGER.info(
        "Drive sync complete. "
        f"{summary['downloaded']} downloaded, "
        f"{summary['skipped_known']} skipped as already synced, "
        f"{summary['skipped_non_image']} skipped as non-image."
    )


def run_cli() -> None:
    try:
        main()
    except FlyerSyncConfigError as exc:
        LOGGER.error(str(exc))
        sys.exit(1)

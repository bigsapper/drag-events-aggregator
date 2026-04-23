"""Shared helpers for crawler config validation and generic scrape utilities."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

VALID_SOURCE_STRATEGIES = {"bracketraces", "racingjunk", "myracepass", "tmccc", "rss"}
DEFAULT_SOURCE_DELAY_SECONDS = {
    "bracketraces": 0.5,
    "racingjunk": 0.75,
}
DEFAULT_SOURCE_MAX_PAGES = {
    "racingjunk": 10,
}
EVENT_PAGE_KEYWORDS = [
    "event", "schedule", "race", "calendar", "upcoming",
    "news", "flyer", "announcement",
]
MIN_WIDTH = 400
MIN_HEIGHT = 400
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DragEventsBot/1.0; fetching public event info)",
}


class ConfigValidationError(ValueError):
    """Raised when a config file is malformed or missing required fields."""


def _load_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(f"Invalid JSON in {path}: {exc.msg}") from exc


def _validate_config_entries(data: object, *, kind: str) -> list[dict]:
    if not isinstance(data, list):
        raise ConfigValidationError(f"{kind} config must be a list of objects")

    validated = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ConfigValidationError(f"{kind}[{index}] must be an object")
        validated.append(entry)
    return validated


def _require_non_empty_string(entry: dict, field: str, *, kind: str, index: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"{kind}[{index}].{field} must be a non-empty string")
    return value


def _require_http_url(entry: dict, field: str, *, kind: str, index: int) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise ConfigValidationError(f"{kind}[{index}].{field} must be an http/https URL")
    return value


def _validate_enabled(entry: dict, *, kind: str, index: int) -> bool:
    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigValidationError(f"{kind}[{index}].enabled must be a boolean when provided")
    return enabled


def _validate_request_headers(entry: dict, *, kind: str, index: int) -> None:
    request_headers = entry.get("request_headers")
    if request_headers is None:
        return
    if not isinstance(request_headers, dict):
        raise ConfigValidationError(f"{kind}[{index}].request_headers must be an object when provided")
    for header_name, header_value in request_headers.items():
        if not isinstance(header_name, str) or not header_name.strip():
            raise ConfigValidationError(f"{kind}[{index}].request_headers keys must be non-empty strings")
        if not isinstance(header_value, str):
            raise ConfigValidationError(f"{kind}[{index}].request_headers values must be strings")


def _validate_optional_non_negative_number(entry: dict, field: str, *, kind: str, index: int) -> None:
    value = entry.get(field)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ConfigValidationError(f"{kind}[{index}].{field} must be a non-negative number when provided")


def _validate_optional_positive_int(entry: dict, field: str, *, kind: str, index: int) -> None:
    value = entry.get(field)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigValidationError(f"{kind}[{index}].{field} must be a positive integer when provided")


def validate_tracks_config(data: object) -> list[dict]:
    validated = []
    for index, entry in enumerate(_validate_config_entries(data, kind="tracks")):
        _require_non_empty_string(entry, "name", kind="tracks", index=index)
        state = entry.get("state")
        _require_http_url(entry, "url", kind="tracks", index=index)
        _validate_enabled(entry, kind="tracks", index=index)
        if not isinstance(state, str) or not re.fullmatch(r"[A-Z]{2}", state):
            raise ConfigValidationError(f"tracks[{index}].state must be a 2-letter uppercase state code")
        validated.append(entry)
    return validated


def validate_sources_config(data: object) -> list[dict]:
    validated = []
    for index, entry in enumerate(_validate_config_entries(data, kind="sources")):
        _require_non_empty_string(entry, "name", kind="sources", index=index)
        _require_http_url(entry, "url", kind="sources", index=index)
        strategy = entry.get("strategy")
        _validate_enabled(entry, kind="sources", index=index)
        _validate_request_headers(entry, kind="sources", index=index)
        _validate_optional_non_negative_number(entry, "page_delay_seconds", kind="sources", index=index)
        _validate_optional_positive_int(entry, "max_pages", kind="sources", index=index)
        if strategy not in VALID_SOURCE_STRATEGIES:
            valid = ", ".join(sorted(VALID_SOURCE_STRATEGIES))
            raise ConfigValidationError(f"sources[{index}].strategy must be one of: {valid}")

        if strategy == "bracketraces":
            event_pages = entry.get("event_pages")
            if not isinstance(event_pages, list) or not event_pages:
                raise ConfigValidationError("sources[{index}].event_pages must be a non-empty list for bracketraces".format(index=index))
            if not all(isinstance(page, str) and page.startswith("/") for page in event_pages):
                raise ConfigValidationError("sources[{index}].event_pages entries must be path strings starting with '/'".format(index=index))

        if strategy == "racingjunk":
            drag_racing_url = entry.get("drag_racing_url")
            if drag_racing_url is not None and (not isinstance(drag_racing_url, str) or not drag_racing_url.startswith(("http://", "https://"))):
                raise ConfigValidationError(f"sources[{index}].drag_racing_url must be an http/https URL when provided")

        validated.append(entry)
    return validated


def load_tracks_config(path: Path) -> list[dict]:
    return [track for track in validate_tracks_config(_load_json_file(path)) if track.get("enabled", True)]


def load_sources_config(path: Path) -> list[dict]:
    return [source for source in validate_sources_config(_load_json_file(path)) if source.get("enabled", True)]


def get_request_headers(source: dict | None = None, base_headers: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(base_headers or DEFAULT_HEADERS)
    if source:
        headers.update(source.get("request_headers", {}))
    return headers


def get_source_delay(source: dict, default: float = 0.0) -> float:
    strategy = source.get("strategy")
    return float(source.get("page_delay_seconds", DEFAULT_SOURCE_DELAY_SECONDS.get(strategy, default)))


def get_source_max_pages(source: dict, default: int = 1) -> int:
    strategy = source.get("strategy")
    return int(source.get("max_pages", DEFAULT_SOURCE_MAX_PAGES.get(strategy, default)))


def is_event_page(url: str, text: str) -> bool:
    combined = (url + " " + text).lower()
    return any(kw in combined for kw in EVENT_PAGE_KEYWORDS)


def get_image_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = []
    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
        if not src:
            continue
        full = urljoin(base_url, src)
        ext = Path(urlparse(full).path).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        try:
            w = int(tag.get("width", 0))
            h = int(tag.get("height", 0))
            if w and h and (w < MIN_WIDTH or h < MIN_HEIGHT):
                continue
        except (ValueError, TypeError):
            pass
        urls.append(full)
    return urls


def find_event_page_urls(soup: BeautifulSoup, base_url: str, home_url: str) -> list[str]:
    home_domain = urlparse(home_url).netloc
    candidates = []
    for tag in soup.find_all("a", href=True):
        href = urljoin(base_url, tag["href"])
        if urlparse(href).netloc != home_domain:
            continue
        if is_event_page(href, tag.get_text(strip=True)):
            candidates.append(href)
    return list(dict.fromkeys(candidates))


def url_to_filename(url: str) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    ext = Path(urlparse(url).path).suffix.lower() or ".jpg"
    slug = re.sub(r"[^\w]", "-", Path(urlparse(url).path).stem)[:40]
    return f"{slug}-{url_hash}{ext}"

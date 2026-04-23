"""HTTP and download helpers for crawler workflows."""

import time
from pathlib import Path

from bs4 import BeautifulSoup


def request_page_impl(url: str, headers: dict[str, str], *, requests_get):
    response = requests_get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response


def request_image_impl(url: str, headers: dict[str, str], *, requests_get):
    response = requests_get(url, headers=headers, timeout=15, stream=True)
    response.raise_for_status()
    return response


def download_image_impl(
    url: str,
    *,
    headers: dict[str, str],
    flyers_dir: Path,
    default_headers: dict[str, str],
    url_to_filename,
    execute_with_retries,
    request_image,
    max_attempts: int,
    base_delay_seconds: float,
    sleep=time.sleep,
    logger,
    log_error,
) -> Path | None:
    filename = url_to_filename(url)
    dest = flyers_dir / filename
    if dest.exists():
        return None

    try:
        resp = execute_with_retries(
            lambda: request_image(url, headers or default_headers),
            category="http",
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            sleep=sleep,
        )
        if "image" not in resp.headers.get("content-type", ""):
            return None
        dest.write_bytes(resp.content)
        return dest
    except Exception as exc:
        logger.error(f"    Download failed {url}: {exc}")
        log_error("download_image", exc, details={"url": url, "destination": dest})
        return None


def fetch_page_impl(
    url: str,
    *,
    headers: dict[str, str],
    default_headers: dict[str, str],
    execute_with_retries,
    request_page,
    max_attempts: int,
    base_delay_seconds: float,
    sleep=time.sleep,
    soup_parser=BeautifulSoup,
    logger,
    log_error,
) -> BeautifulSoup | None:
    try:
        resp = execute_with_retries(
            lambda: request_page(url, headers or default_headers),
            category="http",
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            sleep=sleep,
        )
        return soup_parser(resp.text, "html.parser")
    except Exception as exc:
        logger.error(f"  Could not fetch {url}: {exc}")
        log_error("fetch_page", exc, details={"url": url})
        return None

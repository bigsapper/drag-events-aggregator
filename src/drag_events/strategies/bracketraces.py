"""Bracketraces crawler strategy."""

from pathlib import Path
from urllib.parse import urljoin, urlparse

from ..crawl_utils import IMAGE_EXTENSIONS, get_image_links
from ..logging_utils import get_logger

LOGGER = get_logger(__name__)


def crawl_bracketraces_impl(
    source: dict,
    state: dict,
    *,
    fetch_page,
    download_image,
    headers: dict[str, str],
    delay_seconds: float,
    sleep,
) -> list[Path]:
    base = source["url"]
    downloaded = []
    for path in source.get("event_pages", []):
        url = base + path
        LOGGER.info(f"  {url}")
        soup = fetch_page(url, headers=headers)
        if not soup:
            continue
        image_urls = get_image_links(soup, url)
        for tag in soup.find_all("a", href=True):
            href = urljoin(url, tag["href"])
            ext = Path(urlparse(href).path).suffix.lower()
            if ext in IMAGE_EXTENSIONS and "flyer" in (href + tag.get_text()).lower():
                image_urls.append(href)
        new_urls = [u for u in dict.fromkeys(image_urls) if u not in state["seen_urls"]]
        for img_url in new_urls:
            state["seen_urls"].append(img_url)
            dl = download_image(img_url, headers=headers)
            if dl:
                LOGGER.info(f"    Downloaded: {dl.name}")
                downloaded.append(dl)
        sleep(delay_seconds)
    return downloaded

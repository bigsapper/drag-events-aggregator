"""Track and source crawling orchestration helpers."""

import time
from pathlib import Path


def crawl_track_impl(
    track: dict,
    state: dict,
    *,
    fetch_page,
    find_event_page_urls,
    get_image_links,
    download_image,
    sleep=time.sleep,
    logger,
) -> list[Path]:
    name = track["name"]
    home_url = track["url"]
    logger.info(f"\n{name} ({home_url})")

    home_soup = fetch_page(home_url)
    if not home_soup:
        return []

    pages_to_scan = [home_url] + find_event_page_urls(home_soup, home_url, home_url)
    pages_to_scan = list(dict.fromkeys(pages_to_scan))[:6]

    all_image_urls = []
    for page_url in pages_to_scan:
        soup = home_soup if page_url == home_url else fetch_page(page_url)
        if soup:
            all_image_urls.extend(get_image_links(soup, page_url))
        if page_url != home_url:
            sleep(0.5)

    new_urls = [url for url in dict.fromkeys(all_image_urls) if url not in state["seen_urls"]]
    logger.info(f"  {len(new_urls)} new candidate images across {len(pages_to_scan)} pages")

    downloaded = []
    for url in new_urls:
        state["seen_urls"].append(url)
        path = download_image(url)
        if path:
            logger.info(f"  Downloaded: {path.name}")
            downloaded.append(path)

    return downloaded


def crawl_source_impl(source: dict, state: dict, *, strategy_map: dict[str, object], logger) -> tuple[list[Path], list[dict]]:
    strategy = source.get("strategy")
    if not isinstance(strategy, str):
        logger.warning(f"  Invalid strategy {strategy!r}, skipping.")
        return [], []

    fn = strategy_map.get(strategy)
    if not fn:
        logger.warning(f"  Unknown strategy '{strategy}', skipping.")
        return [], []

    result = fn(source, state)
    if not result:
        return [], []
    if isinstance(result[0], Path):
        return result, []
    return [], result

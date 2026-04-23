"""RacingJunk crawler strategy."""

from ...logging_utils import get_logger
from .common import (
    extract_link_url,
    extract_listing_title,
    extract_text_by_class,
    find_listing_cards,
    record_seen_title,
)

LOGGER = get_logger(__name__)


def crawl_racingjunk_impl(
    source: dict,
    state: dict,
    *,
    fetch_page,
    headers: dict[str, str],
    delay_seconds: float,
    max_pages: int,
    sleep,
) -> list[dict]:
    drag_url = source.get("drag_racing_url", source["url"])
    LOGGER.info(f"  {drag_url}")
    new_events = []
    page = 1

    while page <= max_pages:
        url = f"{drag_url}?page={page}"
        soup = fetch_page(url, headers=headers)
        if not soup:
            break

        cards = find_listing_cards(
            soup,
            primary_selectors=".event-listing, .event-card, article, .listing-item",
            fallback_class_pattern=r"event|listing|card",
        )
        if not cards:
            break

        found_new = False
        for card in cards:
            title = extract_listing_title(card)
            if not record_seen_title(state, "racingjunk_events", title):
                continue
            found_new = True

            new_events.append({
                "title": title,
                "date_text": extract_text_by_class(card, r"date|time"),
                "location_text": extract_text_by_class(card, r"location|venue|city"),
                "source_url": extract_link_url(card, drag_url),
                "source": "RacingJunk",
            })

        if not found_new:
            break
        page += 1
        sleep(delay_seconds)

    LOGGER.info(f"  Found {len(new_events)} new event listings")
    return new_events

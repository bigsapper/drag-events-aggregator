"""MyRacePass crawler strategy."""

from ...logging_utils import get_logger
from .common import (
    extract_link_url,
    extract_listing_title,
    extract_text_by_class,
    find_listing_cards,
    record_seen_title,
)

LOGGER = get_logger(__name__)


def crawl_myracepass_impl(source: dict, state: dict, *, fetch_page, headers: dict[str, str]) -> list[dict]:
    url = source["url"]
    LOGGER.info(f"  {url}")
    new_events = []

    soup = fetch_page(url, headers=headers)
    if not soup:
        return []

    cards = find_listing_cards(
        soup,
        primary_selectors="",
        fallback_class_pattern=r"event|card|listing|schedule",
    )
    for card in cards:
        title = extract_listing_title(card)
        if not record_seen_title(state, "myracepass_events", title):
            continue

        new_events.append({
            "title": title,
            "date_text": extract_text_by_class(card, r"date|time"),
            "event_type_text": extract_text_by_class(card, r"type|category|kind"),
            "source_url": extract_link_url(card, url),
            "source": "MyRacePass",
        })

    LOGGER.info(f"  Found {len(new_events)} new event listings")
    return new_events

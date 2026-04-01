"""RacingJunk crawler strategy."""

import re
from urllib.parse import urljoin


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
    print(f"  {drag_url}")
    new_events = []
    page = 1

    while page <= max_pages:
        url = f"{drag_url}?page={page}"
        soup = fetch_page(url, headers=headers)
        if not soup:
            break

        cards = soup.select(".event-listing, .event-card, article, .listing-item")
        if not cards:
            cards = soup.find_all(attrs={"class": re.compile(r"event|listing|card", re.I)})
        if not cards:
            break

        found_new = False
        for card in cards:
            title_tag = card.find(["h2", "h3", "h4", "a"])
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title or title in state.get("racingjunk_events", []):
                continue
            state.setdefault("racingjunk_events", []).append(title)
            found_new = True

            date_tag = card.find(attrs={"class": re.compile(r"date|time", re.I)})
            location_tag = card.find(attrs={"class": re.compile(r"location|venue|city", re.I)})
            link_tag = card.find("a", href=True)

            new_events.append({
                "title": title,
                "date_text": date_tag.get_text(strip=True) if date_tag else None,
                "location_text": location_tag.get_text(strip=True) if location_tag else None,
                "source_url": urljoin(drag_url, link_tag["href"]) if link_tag else drag_url,
                "source": "RacingJunk",
            })

        if not found_new:
            break
        page += 1
        sleep(delay_seconds)

    print(f"  Found {len(new_events)} new event listings")
    return new_events

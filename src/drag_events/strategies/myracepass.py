"""MyRacePass crawler strategy."""

import re
from urllib.parse import urljoin


def crawl_myracepass_impl(source: dict, state: dict, *, fetch_page, headers: dict[str, str]) -> list[dict]:
    url = source["url"]
    print(f"  {url}")
    new_events = []

    soup = fetch_page(url, headers=headers)
    if not soup:
        return []

    cards = soup.find_all(attrs={"class": re.compile(r"event|card|listing|schedule", re.I)})
    for card in cards:
        title_tag = card.find(["h2", "h3", "h4", "a"])
        title = title_tag.get_text(strip=True) if title_tag else ""
        if not title or title in state.get("myracepass_events", []):
            continue
        state.setdefault("myracepass_events", []).append(title)

        date_tag = card.find(attrs={"class": re.compile(r"date|time", re.I)})
        type_tag = card.find(attrs={"class": re.compile(r"type|category|kind", re.I)})
        link_tag = card.find("a", href=True)

        new_events.append({
            "title": title,
            "date_text": date_tag.get_text(strip=True) if date_tag else None,
            "event_type_text": type_tag.get_text(strip=True) if type_tag else None,
            "source_url": urljoin(url, link_tag["href"]) if link_tag else url,
            "source": "MyRacePass",
        })

    print(f"  Found {len(new_events)} new event listings")
    return new_events

"""Shared helpers for HTML-based event listing crawl strategies."""

import re
from urllib.parse import urljoin


def find_listing_cards(soup, *, primary_selectors: str, fallback_class_pattern: str) -> list:
    if primary_selectors:
        cards = soup.select(primary_selectors)
        if cards:
            return cards
    return soup.find_all(attrs={"class": re.compile(fallback_class_pattern, re.I)})


def extract_listing_title(card) -> str:
    title_tag = card.find(["h2", "h3", "h4", "a"])
    return title_tag.get_text(strip=True) if title_tag else ""


def extract_text_by_class(card, pattern: str) -> str | None:
    tag = card.find(attrs={"class": re.compile(pattern, re.I)})
    return tag.get_text(strip=True) if tag else None


def extract_link_url(card, base_url: str) -> str:
    link_tag = card.find("a", href=True)
    return urljoin(base_url, link_tag["href"]) if link_tag else base_url


def record_seen_title(state: dict, state_key: str, title: str) -> bool:
    seen_titles = state.get(state_key, [])
    if not title or title in seen_titles:
        return False
    state.setdefault(state_key, []).append(title)
    return True

"""TMCCC crawler strategy."""

from bs4 import BeautifulSoup

from ..event_filters import is_in_scope_listing
from ..logging_utils import get_logger

LOGGER = get_logger(__name__)


def parse_tmccc_page_events_impl(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all(attrs={"data-aid": "CALENDAR_SMALLER_SCREEN_CONTAINER"})
    merged: dict[str, dict] = {}

    for card in cards:
        date_block = card.find(attrs={"data-aid": "CALENDAR_EVENT_DATE"})
        title_tag = card.find(attrs={"data-aid": "CALENDAR_EVENT_TITLE"})
        if not date_block or not title_tag:
            continue

        date_text = date_block.get_text(" ", strip=True)
        title = title_tag.get_text(" ", strip=True)
        if not title or not date_text:
            continue
        if not is_in_scope_listing({"title": title}):
            continue

        time_block = card.find(attrs={"data-aid": "CALENDAR_EVENT_TIME"})
        time_text = location_text = None
        if time_block:
            parts = [node.get_text(" ", strip=True) for node in time_block.find_all(["h4", "p"])]
            parts = [part for part in parts if part]
            if parts:
                time_text = " ".join(parts[:-1]) if len(parts) > 1 else parts[0]
                location_text = parts[-1] if len(parts) > 1 else None

        desc_block = card.find(attrs={"data-aid": "CALENDAR_DESC_TEXT"})
        desc_text = desc_block.get_text(separator="\n", strip=True) if desc_block else None

        key = f"{title}|{date_text}"
        existing = merged.get(key)
        if existing:
            existing["time_text"] = existing["time_text"] or time_text
            existing["location_text"] = existing["location_text"] or location_text
            existing["description"] = existing["description"] or desc_text
            continue

        merged[key] = {
            "title": title,
            "date_text": date_text,
            "time_text": time_text,
            "location_text": location_text,
            "description": desc_text,
        }

    return list(merged.values())


def tmccc_event_key(event: dict) -> str:
    return f"{event['title']}|{event['date_text']}"


def advance_tmccc_calendar_impl(page, current_keys: list[str]) -> bool:
    next_btn = page.locator("[data-aid='CALENDAR_SHOW_NEXT_EVENTS']")
    if next_btn.count() == 0:
        return False

    button = next_btn.first
    if hasattr(button, "is_visible") and not button.is_visible():
        return False
    if hasattr(button, "is_disabled") and button.is_disabled():
        return False

    previous_last_key = current_keys[-1] if current_keys else ""
    button.scroll_into_view_if_needed()
    button.click()
    if previous_last_key:
        page.wait_for_function(
            """
            (prevKey) => {
              const cards = Array.from(
                document.querySelectorAll("[data-aid='CALENDAR_SMALLER_SCREEN_CONTAINER']")
              );
              const keys = cards.map((card) => {
                const title = card.querySelector("[data-aid='CALENDAR_EVENT_TITLE']")?.textContent?.trim() || "";
                const date = card.querySelector("[data-aid='CALENDAR_EVENT_DATE']")?.textContent?.trim() || "";
                return title && date ? `${title}|${date}` : "";
              }).filter(Boolean);
              return keys.length > 0 && keys[keys.length - 1] !== prevKey;
            }
            """,
            arg=previous_last_key,
            timeout=10000,
        )
    else:
        page.wait_for_selector("[data-aid='CALENDAR_EVENT_TITLE']", state="attached", timeout=10000)
    return True


def crawl_tmccc_impl(
    source: dict,
    state: dict,
    *,
    headers: dict[str, str],
    parse_page_events,
    event_key,
    advance_calendar,
) -> list[dict]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

    url = source["url"]
    LOGGER.info(f"  {url}")

    all_raw = []
    seen_page_signatures = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900}, extra_http_headers=headers)
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_selector("[data-aid='CALENDAR_EVENT_TITLE']", state="attached", timeout=15000)

        while True:
            page_events = parse_page_events(page.content())
            current_keys = [event_key(event) for event in page_events]
            page_signature = tuple(current_keys)
            if page_signature and page_signature not in seen_page_signatures:
                all_raw.extend(page_events)
                seen_page_signatures.add(page_signature)

            try:
                if not advance_calendar(page, current_keys):
                    break
            except PlaywrightTimeoutError:
                break

        browser.close()

    new_events = []
    for event in all_raw:
        key = event_key(event)
        if key in state.get("tmccc_events", []):
            continue
        state.setdefault("tmccc_events", []).append(key)

        new_events.append({
            **event,
            "source_url": url,
            "source": "TMCCC",
        })

    LOGGER.info(f"  Found {len(new_events)} new event listings")
    return new_events

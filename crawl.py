"""Crawl track websites and event aggregators for drag racing flyer images.

Two source types:
  tracks.json   — individual track websites (generic image scraper)
  sources.json  — aggregator sites with custom strategies per source

Usage:
    python crawl.py                        # crawl all tracks + all sources
    python crawl.py --tracks               # track websites only
    python crawl.py --sources              # aggregator sources only
    python crawl.py --track "Texas Motorplex"   # one track by name
    python crawl.py --source "Bracketraces.com" # one source by name
"""

import hashlib
import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

import process
from dedup import find_same_event, merge_events
from extract_text import extract_from_text

TRACKS_FILE  = Path(__file__).parent / "tracks.json"
SOURCES_FILE = Path(__file__).parent / "sources.json"
FLYERS_DIR   = Path(__file__).parent / "flyers"
CRAWL_STATE  = Path(__file__).parent / ".crawl_state.json"

FLYERS_DIR.mkdir(exist_ok=True)

# Pages on a track site most likely to contain event flyers
EVENT_PAGE_KEYWORDS = [
    "event", "schedule", "race", "calendar", "upcoming",
    "news", "flyer", "announcement"
]

# Minimum image dimensions to be considered a flyer (filters out icons/logos)
MIN_WIDTH  = 400
MIN_HEIGHT = 400

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DragEventsBot/1.0; fetching public event info)"
}


# ── State management ──────────────────────────────────────────────────────────

def load_state() -> dict:
    if CRAWL_STATE.exists():
        return json.loads(CRAWL_STATE.read_text())
    return {"seen_urls": [], "racingjunk_events": [], "myracepass_events": []}


def save_state(state: dict) -> None:
    CRAWL_STATE.write_text(json.dumps(state, indent=2))


# ── Shared helpers ────────────────────────────────────────────────────────────

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


def download_image(url: str) -> Path | None:
    filename = url_to_filename(url)
    dest = FLYERS_DIR / filename
    if dest.exists():
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, stream=True)
        resp.raise_for_status()
        if "image" not in resp.headers.get("content-type", ""):
            return None
        dest.write_bytes(resp.content)
        return dest
    except Exception as e:
        print(f"    Download failed {url}: {e}")
        return None


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  Could not fetch {url}: {e}")
        return None


# ── Track website crawler (generic) ──────────────────────────────────────────

def crawl_track(track: dict, state: dict) -> list[Path]:
    name = track["name"]
    home_url = track["url"]
    print(f"\n{name} ({home_url})")

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
            time.sleep(0.5)

    new_urls = [u for u in dict.fromkeys(all_image_urls) if u not in state["seen_urls"]]
    print(f"  {len(new_urls)} new candidate images across {len(pages_to_scan)} pages")

    downloaded = []
    for url in new_urls:
        state["seen_urls"].append(url)
        path = download_image(url)
        if path:
            print(f"  Downloaded: {path.name}")
            downloaded.append(path)

    return downloaded


# ── Source strategies ─────────────────────────────────────────────────────────

def crawl_bracketraces(source: dict, state: dict) -> list[Path]:
    """Scrape individual Bracketraces.com event pages for flyer images."""
    base = source["url"]
    downloaded = []
    for path in source.get("event_pages", []):
        url = base + path
        print(f"  {url}")
        soup = fetch_page(url)
        if not soup:
            continue
        image_urls = get_image_links(soup, url)
        # Also look for links with "flyer" in the text or href
        for tag in soup.find_all("a", href=True):
            href = urljoin(url, tag["href"])
            ext = Path(urlparse(href).path).suffix.lower()
            if ext in IMAGE_EXTENSIONS and "flyer" in (href + tag.get_text()).lower():
                image_urls.append(href)
        new_urls = [u for u in dict.fromkeys(image_urls) if u not in state["seen_urls"]]
        for img_url in new_urls:
            state["seen_urls"].append(img_url)
            dl = download_image(img_url)
            if dl:
                print(f"    Downloaded: {dl.name}")
                downloaded.append(dl)
        time.sleep(0.5)
    return downloaded


def crawl_racingjunk(source: dict, state: dict) -> list[dict]:
    """Scrape RacingJunk drag racing events. Returns structured text records (no flyers)."""
    drag_url = source.get("drag_racing_url", source["url"])
    print(f"  {drag_url}")
    new_events = []
    page = 1

    while page <= 10:  # cap at 10 pages (~200 events)
        url = f"{drag_url}?page={page}"
        soup = fetch_page(url)
        if not soup:
            break

        cards = soup.select(".event-listing, .event-card, article, .listing-item")
        if not cards:
            # Try generic fallback: any element with a date and title
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
                "source": "RacingJunk"
            })

        if not found_new:
            break
        page += 1
        time.sleep(0.75)

    print(f"  Found {len(new_events)} new event listings")
    return new_events


def crawl_myracepass(source: dict, state: dict) -> list[dict]:
    """Scrape MyRacePass event listings from public HTML pages."""
    url = source["url"]
    print(f"  {url}")
    new_events = []

    soup = fetch_page(url)
    if not soup:
        return []

    # MyRacePass renders events as cards with track name, event type, date
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
            "source": "MyRacePass"
        })

    print(f"  Found {len(new_events)} new event listings")
    return new_events


def crawl_rss(source: dict, state: dict) -> list[dict]:
    """Parse an RSS feed for event announcements."""
    url = source["url"]
    print(f"  {url}")
    feed = feedparser.parse(url)
    new_items = []
    for entry in feed.entries:
        link = entry.get("link", "")
        if link in state.get("seen_urls", []):
            continue
        state.setdefault("seen_urls", []).append(link)
        new_items.append({
            "title": entry.get("title", ""),
            "published": entry.get("published", ""),
            "summary": entry.get("summary", ""),
            "source_url": link,
            "source": source["name"]
        })
    print(f"  Found {len(new_items)} new RSS items")
    return new_items


STRATEGY_MAP = {
    "bracketraces": crawl_bracketraces,
    "racingjunk":   crawl_racingjunk,
    "myracepass":   crawl_myracepass,
    "rss":          crawl_rss,
}


def crawl_source(source: dict, state: dict) -> tuple[list[Path], list[dict]]:
    """Dispatch to the correct strategy.
    Returns (image_paths, text_listings) — only one will be non-empty per source.
    """
    strategy = source.get("strategy")
    fn = STRATEGY_MAP.get(strategy)
    if not fn:
        print(f"  Unknown strategy '{strategy}', skipping.")
        return [], []
    result = fn(source, state)
    if not result:
        return [], []
    if isinstance(result[0], Path):
        return result, []
    return [], result


# ── Main ──────────────────────────────────────────────────────────────────────

def run_extraction(downloaded: list[Path], text_listings: list[dict]) -> None:
    if not downloaded and not text_listings:
        return

    events = process.load_events()
    counts = {"new": 0, "merged": 0, "duplicate": 0, "error": 0}

    # Image flyers → Claude vision
    if downloaded:
        print("\nRunning vision extraction on new flyers...")
    for path in downloaded:
        print(f"\nProcessing: {path.name}")
        try:
            outcome, event = process.process_flyer(str(path), events)
            counts[outcome] += 1
            label = {"new": "NEW", "merged": "UPDATED", "duplicate": "SKIPPED"}[outcome]
            print(f"  [{label}] {event.get('title', '?')} — {event.get('track', {}).get('name', '?')}")
            if "test-flyers" not in path.parts:
                path.unlink()
        except Exception as e:
            print(f"  [ERROR] {e}")
            counts["error"] += 1

    # Text listings → Claude text (haiku)
    if text_listings:
        print(f"\nParsing {len(text_listings)} text listings...")
    for listing in text_listings:
        title = listing.get("title", "?")
        print(f"\nParsing: {title}")
        try:
            extracted = extract_from_text(listing)

            # Check for same event already in DB
            same = find_same_event(extracted, events)
            if same:
                flyer_entry = {"file": listing.get("source_url", ""), "phash": None,
                               "processed_at": datetime.now(timezone.utc).isoformat()}
                merged = merge_events(same, extracted, flyer_entry)
                merged["updated_at"] = datetime.now(timezone.utc).isoformat()
                idx = next(i for i, e in enumerate(events) if e["id"] == same["id"])
                events[idx] = merged
                counts["merged"] += 1
                print(f"  [UPDATED] {merged.get('title', '?')}")
            else:
                new_event = {
                    "id": str(uuid.uuid4()),
                    **extracted,
                    "flyers": [{"file": listing.get("source_url", ""), "phash": None,
                                "processed_at": datetime.now(timezone.utc).isoformat()}],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                events.append(new_event)
                counts["new"] += 1
                print(f"  [NEW] {new_event.get('title', '?')} — {new_event.get('track', {}).get('name', '?')}")
        except Exception as e:
            print(f"  [ERROR] {e}")
            counts["error"] += 1

    process.save_events(events)
    print(f"\n{len(events)} total events in database.")
    print(f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  {counts['error']} errors")


def main():
    args = sys.argv[1:]

    run_tracks  = "--sources" not in args
    run_sources = "--tracks"  not in args

    track_filter  = None
    source_filter = None
    for i, arg in enumerate(args):
        if arg == "--track"  and i + 1 < len(args): track_filter  = args[i + 1].lower()
        if arg == "--source" and i + 1 < len(args): source_filter = args[i + 1].lower()

    state = load_state()
    total_downloaded = []

    if run_tracks:
        tracks = json.loads(TRACKS_FILE.read_text())
        if track_filter:
            tracks = [t for t in tracks if track_filter in t["name"].lower()]
        print(f"=== Track websites ({len(tracks)}) ===")
        for track in tracks:
            files = crawl_track(track, state)
            total_downloaded.extend(files)
            save_state(state)
            time.sleep(1)

    total_text_listings = []

    if run_sources:
        sources = json.loads(SOURCES_FILE.read_text())
        if source_filter:
            sources = [s for s in sources if source_filter in s["name"].lower()]
        print(f"\n=== Aggregator sources ({len(sources)}) ===")
        for source in sources:
            print(f"\n{source['name']}")
            files, listings = crawl_source(source, state)
            total_downloaded.extend(files)
            total_text_listings.extend(listings)
            save_state(state)
            time.sleep(1)

    print(f"\n{'─' * 50}")
    print(f"Crawl complete. {len(total_downloaded)} new flyer images, {len(total_text_listings)} text listings.")
    run_extraction(total_downloaded, total_text_listings)


if __name__ == "__main__":
    main()

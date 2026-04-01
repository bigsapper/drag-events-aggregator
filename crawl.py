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
import math
import os
import re
import statistics
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

import process
from dedup import find_same_event, merge_events, track_slug
from extract_text import extract_from_text

TRACKS_FILE  = Path(__file__).parent / "tracks.json"
SOURCES_FILE = Path(__file__).parent / "sources.json"
FLYERS_DIR   = Path(__file__).parent / "flyers"
DIST_DIR     = Path(__file__).parent / "dist"
RUNTIME_DIR  = Path(__file__).parent / "runtime"
STATE_DIR    = RUNTIME_DIR / "state"
TRACING_DIR  = RUNTIME_DIR / "tracing"
CRAWL_STATE  = STATE_DIR / "crawl_state.json"
METRICS_LOG  = TRACING_DIR / "crawl_metrics.jsonl"
METRICS_SUMMARY = TRACING_DIR / "crawl_metrics_summary.json"
ERROR_LOG    = TRACING_DIR / "crawl_errors.log"

LEGACY_CRAWL_STATE = Path(__file__).parent / ".crawl_state.json"
LEGACY_METRICS_LOG = DIST_DIR / "crawl_metrics.jsonl"
LEGACY_METRICS_SUMMARY = DIST_DIR / "crawl_metrics_summary.json"
LEGACY_ERROR_LOG = DIST_DIR / "crawl_errors.log"
RUNTIME_LEGACY_METRICS_LOG = RUNTIME_DIR / "crawl_metrics.jsonl"
RUNTIME_LEGACY_METRICS_SUMMARY = RUNTIME_DIR / "crawl_metrics_summary.json"
RUNTIME_LEGACY_ERROR_LOG = RUNTIME_DIR / "crawl_errors.log"

FLYERS_DIR.mkdir(exist_ok=True)
DIST_DIR.mkdir(exist_ok=True)
RUNTIME_DIR.mkdir(exist_ok=True)
STATE_DIR.mkdir(exist_ok=True)
TRACING_DIR.mkdir(exist_ok=True)

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

def ensure_runtime_layout() -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)
    TRACING_DIR.mkdir(exist_ok=True)
    legacy_files = [
        (LEGACY_CRAWL_STATE, CRAWL_STATE),
        (LEGACY_METRICS_LOG, METRICS_LOG),
        (LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
        (LEGACY_ERROR_LOG, ERROR_LOG),
        (RUNTIME_LEGACY_METRICS_LOG, METRICS_LOG),
        (RUNTIME_LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
        (RUNTIME_LEGACY_ERROR_LOG, ERROR_LOG),
    ]
    for legacy, current in legacy_files:
        if legacy.exists() and not current.exists():
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(current)

def load_state() -> dict:
    ensure_runtime_layout()
    if CRAWL_STATE.exists():
        return json.loads(CRAWL_STATE.read_text())
    return {"seen_urls": [], "racingjunk_events": [], "myracepass_events": [], "tmccc_events": []}


def save_state(state: dict) -> None:
    ensure_runtime_layout()
    CRAWL_STATE.write_text(json.dumps(state, indent=2))


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def summarize_metrics(entries: list[dict]) -> dict:
    successful = [entry for entry in entries if entry.get("status") == "success"]
    durations = [entry["elapsed_seconds"] for entry in successful if isinstance(entry.get("elapsed_seconds"), (int, float))]

    summary = {
        "recorded_runs": len(entries),
        "successful_runs": len(successful),
        "last_run": entries[-1] if entries else None,
    }
    if not durations:
        return summary

    summary.update({
        "average_seconds": round(sum(durations) / len(durations), 2),
        "median_seconds": round(statistics.median(durations), 2),
        "min_seconds": round(min(durations), 2),
        "max_seconds": round(max(durations), 2),
    })
    if len(durations) >= 2:
        sorted_durations = sorted(durations)
        index = math.ceil(0.95 * len(sorted_durations)) - 1
        summary["p95_seconds"] = round(sorted_durations[max(index, 0)], 2)
    return summary


def load_metric_entries(metrics_log: Path = METRICS_LOG) -> list[dict]:
    ensure_runtime_layout()
    if not metrics_log.exists():
        return []

    decoder = json.JSONDecoder()
    entries = []
    for line in metrics_log.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        entries.append(decoder.decode(line))
    return entries


def record_run_metrics(run_metrics: dict, metrics_log: Path = METRICS_LOG, summary_file: Path = METRICS_SUMMARY) -> dict:
    ensure_runtime_layout()
    metrics_log.parent.mkdir(parents=True, exist_ok=True)
    with metrics_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run_metrics) + "\n")

    entries = load_metric_entries(metrics_log)
    summary = summarize_metrics(entries)
    summary_file.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def should_record_runtime_metrics() -> bool:
    return "PYTEST_CURRENT_TEST" not in os.environ


def should_log_errors(details: dict | None = None) -> bool:
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    if not details:
        return True

    for value in details.values():
        value_str = str(value)
        if "test-flyers" in value_str:
            return False
    return True


def get_error_log_path() -> Path:
    return ERROR_LOG


def log_error(context: str, error: Exception | str, *, error_log: Path | None = None, details: dict | None = None, include_traceback: bool = False) -> None:
    if not should_log_errors(details):
        return
    ensure_runtime_layout()
    if error_log is None:
        error_log = get_error_log_path()
    error_log.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with error_log.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {context}\n")
        fh.write(f"error: {error}\n")
        if details:
            for key, value in details.items():
                fh.write(f"{key}: {value}\n")
        if include_traceback and isinstance(error, BaseException):
            fh.write(traceback.format_exc())
            if not traceback.format_exc().endswith("\n"):
                fh.write("\n")
        fh.write("\n")


def print_metrics_summary(summary: dict) -> None:
    if not summary.get("recorded_runs"):
        print("No crawl metrics recorded yet.")
        return

    print("Crawl metrics summary")
    print(f"  recorded runs:   {summary['recorded_runs']}")
    print(f"  successful runs: {summary.get('successful_runs', 0)}")

    if summary.get("average_seconds") is not None:
        print(f"  average runtime: {format_duration(summary['average_seconds'])}")
        print(f"  median runtime:  {format_duration(summary['median_seconds'])}")
        print(f"  min runtime:     {format_duration(summary['min_seconds'])}")
        print(f"  max runtime:     {format_duration(summary['max_seconds'])}")
        if summary.get("p95_seconds") is not None:
            print(f"  p95 runtime:     {format_duration(summary['p95_seconds'])}")

    last_run = summary.get("last_run")
    if last_run:
        status = last_run.get("status", "unknown")
        started = last_run.get("started_at", "?")
        elapsed = format_duration(last_run.get("elapsed_seconds", 0))
        print(f"  last run:        {status} at {started} ({elapsed})")


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
        log_error("download_image", e, details={"url": url, "destination": dest})
        return None


def fetch_page(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  Could not fetch {url}: {e}")
        log_error("fetch_page", e, details={"url": url})
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


def parse_tmccc_page_events(html: str) -> list[dict]:
    """Extract and merge TMCCC calendar cards from one rendered page of HTML."""
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


def _tmccc_event_key(event: dict) -> str:
    return f"{event['title']}|{event['date_text']}"


def _advance_tmccc_calendar(page, current_keys: list[str]) -> bool:
    """Click TMCCC's More Events control and wait for the visible event set to change."""
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


def crawl_tmccc(source: dict, state: dict) -> list[dict]:
    """Scrape TMCCC event calendar (GoDaddy site builder).

    Uses Playwright to page through the calendar using CALENDAR_SHOW_NEXT_EVENTS,
    scraping each page until there is no next arrow (end of calendar).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

    url = source["url"]
    print(f"  {url}")

    all_raw = []
    seen_page_signatures = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_selector("[data-aid='CALENDAR_EVENT_TITLE']", state="attached", timeout=15000)

        while True:
            page_events = parse_tmccc_page_events(page.content())
            current_keys = [_tmccc_event_key(event) for event in page_events]
            page_signature = tuple(current_keys)
            if page_signature and page_signature not in seen_page_signatures:
                all_raw.extend(page_events)
                seen_page_signatures.add(page_signature)

            try:
                if not _advance_tmccc_calendar(page, current_keys):
                    break
            except PlaywrightTimeoutError:
                break

        browser.close()

    new_events = []
    for event in all_raw:
        key = _tmccc_event_key(event)
        if key in state.get("tmccc_events", []):
            continue
        state.setdefault("tmccc_events", []).append(key)

        new_events.append({
            **event,
            "source_url": url,
            "source": "TMCCC",
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
    "tmccc":        crawl_tmccc,
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

def run_extraction(downloaded: list[Path], text_listings: list[dict]) -> dict:
    start = time.perf_counter()
    if not downloaded and not text_listings:
        return {
            "elapsed_seconds": 0.0,
            "image_flyers": 0,
            "text_listings": 0,
            "new": 0,
            "merged": 0,
            "duplicate": 0,
            "error": 0,
            "total_events": 0,
        }

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
            log_error("run_extraction.process_flyer", e, details={"flyer_path": path}, include_traceback=True)

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
                track = extracted.get("track") or {}
                extracted["track"] = {
                    "id":    track_slug(track.get("name"), track.get("state")),
                    "name":  track.get("name"),
                    "city":  track.get("city"),
                    "state": track.get("state"),
                }
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
            log_error(
                "run_extraction.extract_from_text",
                e,
                details={"listing_title": title, "source_url": listing.get("source_url", "")},
                include_traceback=True,
            )

    process.save_events(events)
    print(f"\n{len(events)} total events in database.")
    print(f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  {counts['error']} errors")
    return {
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "image_flyers": len(downloaded),
        "text_listings": len(text_listings),
        "new": counts["new"],
        "merged": counts["merged"],
        "duplicate": counts["duplicate"],
        "error": counts["error"],
        "total_events": len(events),
    }


def main():
    args = sys.argv[1:]

    if "--metrics" in args:
        print_metrics_summary(summarize_metrics(load_metric_entries()))
        return

    track_filter  = None
    source_filter = None
    for i, arg in enumerate(args):
        if arg == "--track"  and i + 1 < len(args): track_filter  = args[i + 1].lower()
        if arg == "--source" and i + 1 < len(args): source_filter = args[i + 1].lower()

    run_tracks  = "--sources" not in args and source_filter is None
    run_sources = "--tracks"  not in args and track_filter  is None
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    run_metrics = {
        "run_id": started_at.strftime("%Y%m%d-%H%M%S"),
        "started_at": started_at.isoformat(),
        "status": "success",
        "args": args,
        "filters": {"track": track_filter, "source": source_filter},
        "tracks": [],
        "sources": [],
    }

    try:
        state = load_state()
        total_downloaded = []
        total_text_listings = []

        tracks = []
        sources = []

        if run_tracks:
            tracks = json.loads(TRACKS_FILE.read_text())
            if track_filter:
                tracks = [t for t in tracks if track_filter in t["name"].lower()]
            print(f"=== Track websites ({len(tracks)}) ===")
            for track in tracks:
                item_start = time.perf_counter()
                files = crawl_track(track, state)
                elapsed = round(time.perf_counter() - item_start, 2)
                total_downloaded.extend(files)
                run_metrics["tracks"].append({
                    "name": track["name"],
                    "elapsed_seconds": elapsed,
                    "downloaded_images": len(files),
                })
                save_state(state)
                time.sleep(1)

        if run_sources:
            sources = json.loads(SOURCES_FILE.read_text())
            if source_filter:
                sources = [s for s in sources if source_filter in s["name"].lower()]
            print(f"\n=== Aggregator sources ({len(sources)}) ===")
            for source in sources:
                print(f"\n{source['name']}")
                item_start = time.perf_counter()
                files, listings = crawl_source(source, state)
                elapsed = round(time.perf_counter() - item_start, 2)
                total_downloaded.extend(files)
                total_text_listings.extend(listings)
                run_metrics["sources"].append({
                    "name": source["name"],
                    "strategy": source.get("strategy"),
                    "elapsed_seconds": elapsed,
                    "downloaded_images": len(files),
                    "text_listings": len(listings),
                })
                save_state(state)
                time.sleep(1)

        print(f"\n{'─' * 50}")
        print(f"Crawl complete. {len(total_downloaded)} new flyer images, {len(total_text_listings)} text listings.")
        extraction_metrics = run_extraction(total_downloaded, total_text_listings)
        if not isinstance(extraction_metrics, dict):
            extraction_metrics = {}
        run_metrics["selection"] = {
            "run_tracks": run_tracks,
            "run_sources": run_sources,
            "track_count": len(tracks),
            "source_count": len(sources),
        }
        run_metrics["crawl_counts"] = {
            "downloaded_images": len(total_downloaded),
            "text_listings": len(total_text_listings),
        }
        run_metrics["extraction"] = extraction_metrics
    except Exception as exc:
        run_metrics["status"] = "error"
        run_metrics["error"] = str(exc)
        log_error("crawl.main", exc, details={"args": args}, include_traceback=True)
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        run_metrics["finished_at"] = finished_at.isoformat()
        run_metrics["elapsed_seconds"] = round(time.perf_counter() - started_perf, 2)
        if not should_record_runtime_metrics():
            return
        summary = record_run_metrics(run_metrics)
        print(f"\nRecorded crawl metrics in {METRICS_LOG}")
        print(f"Error log file: {ERROR_LOG}")
        if summary.get("average_seconds") is not None:
            print(
                "Historical runtime: "
                f"avg {format_duration(summary['average_seconds'])}, "
                f"median {format_duration(summary['median_seconds'])}, "
                f"last {format_duration(run_metrics['elapsed_seconds'])}"
            )


if __name__ == "__main__":
    main()

"""Crawl track websites and event aggregators for drag racing flyer images.

Two source types:
  src/drag_events/config/tracks.json   — individual track websites (generic image scraper)
  src/drag_events/config/sources.json  — aggregator sites with custom strategies per source

Usage:
    python -m drag_events.crawl                        # crawl all tracks + all sources
    python -m drag_events.crawl --tracks               # track websites only
    python -m drag_events.crawl --sources              # aggregator sources only
    python -m drag_events.crawl --track "Texas Motorplex"   # one track by name
    python -m drag_events.crawl --source "Bracketraces.com" # one source by name
"""

import json
import os
import re
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

from . import process
from .crawl_utils import (
    DEFAULT_HEADERS as HEADERS,
    ConfigValidationError,
    find_event_page_urls,
    get_image_links,
    get_request_headers,
    get_source_delay,
    get_source_max_pages,
    is_event_page,
    validate_sources_config,
    validate_tracks_config,
    load_sources_config as _load_sources_config,
    load_tracks_config as _load_tracks_config,
    url_to_filename,
)
from .crawl_runtime import (
    ensure_runtime_layout_impl,
    format_duration as _format_duration,
    get_error_log_path as _get_error_log_path,
    load_metric_entries_impl,
    load_state_impl,
    log_error_impl,
    print_metrics_summary as _print_metrics_summary,
    record_run_metrics_impl,
    save_state_impl,
    should_log_errors as _should_log_errors,
    should_record_runtime_metrics as _should_record_runtime_metrics,
    summarize_metrics as _summarize_metrics,
)
from .dedup import find_same_event, merge_events, track_slug
from .event_filters import is_in_scope_event, is_in_scope_listing, is_past_event
from .extract_text import extract_from_text
from .logging_utils import get_logger
from .retry_utils import execute_with_retries, get_retry_telemetry, reset_retry_telemetry
from .strategies.bracketraces import crawl_bracketraces_impl
from .strategies.myracepass import crawl_myracepass_impl
from .strategies.racingjunk import crawl_racingjunk_impl
from .strategies.rss import crawl_rss_impl
from .strategies.tmccc import (
    advance_tmccc_calendar_impl,
    crawl_tmccc_impl,
    parse_tmccc_page_events_impl,
    tmccc_event_key,
)
from .tmccc_enrichment import enrich_tmccc_extracted_event

BASE_DIR     = Path(__file__).resolve().parents[2]
CONFIG_DIR   = BASE_DIR / "src" / "drag_events" / "config"
TRACKS_FILE  = CONFIG_DIR / "tracks.json"
SOURCES_FILE = CONFIG_DIR / "sources.json"
FLYERS_DIR   = BASE_DIR / "flyers"
DIST_DIR     = BASE_DIR / "dist"
RUNTIME_DIR  = BASE_DIR / "runtime"
STATE_DIR    = RUNTIME_DIR / "state"
TRACING_DIR  = RUNTIME_DIR / "tracing"
CRAWL_STATE  = STATE_DIR / "crawl_state.json"
METRICS_LOG  = TRACING_DIR / "crawl_metrics.jsonl"
METRICS_SUMMARY = TRACING_DIR / "crawl_metrics_summary.json"
ERROR_LOG    = TRACING_DIR / "crawl_errors.log"

LEGACY_CRAWL_STATE = BASE_DIR / ".crawl_state.json"
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

HTTP_MAX_ATTEMPTS = 3
HTTP_RETRY_BASE_DELAY_SECONDS = 1.0
LOGGER = get_logger(__name__)


# ── State management ──────────────────────────────────────────────────────────

def ensure_runtime_layout() -> None:
    ensure_runtime_layout_impl(
        RUNTIME_DIR,
        STATE_DIR,
        TRACING_DIR,
        [
            (LEGACY_CRAWL_STATE, CRAWL_STATE),
            (LEGACY_METRICS_LOG, METRICS_LOG),
            (LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
            (LEGACY_ERROR_LOG, ERROR_LOG),
            (RUNTIME_LEGACY_METRICS_LOG, METRICS_LOG),
            (RUNTIME_LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
            (RUNTIME_LEGACY_ERROR_LOG, ERROR_LOG),
        ],
    )

def load_state() -> dict:
    return load_state_impl(CRAWL_STATE, ensure_runtime_layout=ensure_runtime_layout, json_loads=json.loads)


def save_state(state: dict) -> None:
    save_state_impl(CRAWL_STATE, state, ensure_runtime_layout=ensure_runtime_layout, json_dumps=json.dumps)


def format_duration(seconds: float) -> str:
    return _format_duration(seconds)


def summarize_metrics(entries: list[dict]) -> dict:
    return _summarize_metrics(entries)


def load_metric_entries(metrics_log: Path = METRICS_LOG) -> list[dict]:
    return load_metric_entries_impl(metrics_log, ensure_runtime_layout=ensure_runtime_layout)


def record_run_metrics(run_metrics: dict, metrics_log: Path = METRICS_LOG, summary_file: Path = METRICS_SUMMARY) -> dict:
    return record_run_metrics_impl(
        run_metrics,
        metrics_log=metrics_log,
        summary_file=summary_file,
        ensure_runtime_layout=ensure_runtime_layout,
        load_metric_entries=load_metric_entries,
        summarize_metrics=summarize_metrics,
    )


def should_record_runtime_metrics() -> bool:
    return _should_record_runtime_metrics(os.environ)


def should_log_errors(details: dict | None = None) -> bool:
    return _should_log_errors(details, env=os.environ)


def get_error_log_path() -> Path:
    return _get_error_log_path(ERROR_LOG)


def log_error(context: str, error: Exception | str, *, error_log: Path | None = None, details: dict | None = None, include_traceback: bool = False) -> None:
    log_error_impl(
        context,
        error,
        error_log=error_log,
        details=details,
        include_traceback=include_traceback,
        should_log_errors=should_log_errors,
        ensure_runtime_layout=ensure_runtime_layout,
        get_error_log_path=get_error_log_path,
        traceback_format_exc=traceback.format_exc,
    )


def print_metrics_summary(summary: dict) -> None:
    _print_metrics_summary(summary, format_duration=format_duration)


# ── Config validation ─────────────────────────────────────────────────────────

def load_tracks_config(path: Path = TRACKS_FILE) -> list[dict]:
    return _load_tracks_config(path)


def load_sources_config(path: Path = SOURCES_FILE) -> list[dict]:
    return _load_sources_config(path)


def download_image(url: str, headers: dict[str, str] | None = None) -> Path | None:
    filename = url_to_filename(url)
    dest = FLYERS_DIR / filename
    if dest.exists():
        return None
    try:
        resp = execute_with_retries(
            lambda: _request_image(url, headers or HEADERS),
            category="http",
            max_attempts=HTTP_MAX_ATTEMPTS,
            base_delay_seconds=HTTP_RETRY_BASE_DELAY_SECONDS,
            sleep=time.sleep,
        )
        if "image" not in resp.headers.get("content-type", ""):
            return None
        dest.write_bytes(resp.content)
        return dest
    except Exception as e:
        LOGGER.error(f"    Download failed {url}: {e}")
        log_error("download_image", e, details={"url": url, "destination": dest})
        return None


def fetch_page(url: str, headers: dict[str, str] | None = None) -> BeautifulSoup | None:
    try:
        resp = execute_with_retries(
            lambda: _request_page(url, headers or HEADERS),
            category="http",
            max_attempts=HTTP_MAX_ATTEMPTS,
            base_delay_seconds=HTTP_RETRY_BASE_DELAY_SECONDS,
            sleep=time.sleep,
        )
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        LOGGER.error(f"  Could not fetch {url}: {e}")
        log_error("fetch_page", e, details={"url": url})
        return None


# ── Track website crawler (generic) ──────────────────────────────────────────

def crawl_track(track: dict, state: dict) -> list[Path]:
    name = track["name"]
    home_url = track["url"]
    LOGGER.info(f"\n{name} ({home_url})")

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
    LOGGER.info(f"  {len(new_urls)} new candidate images across {len(pages_to_scan)} pages")

    downloaded = []
    for url in new_urls:
        state["seen_urls"].append(url)
        path = download_image(url)
        if path:
            LOGGER.info(f"  Downloaded: {path.name}")
            downloaded.append(path)

    return downloaded


# ── Source strategies ─────────────────────────────────────────────────────────

def crawl_bracketraces(source: dict, state: dict) -> list[Path]:
    """Scrape individual Bracketraces.com event pages for flyer images."""
    return crawl_bracketraces_impl(
        source,
        state,
        fetch_page=fetch_page,
        download_image=download_image,
        headers=get_request_headers(source),
        delay_seconds=get_source_delay(source),
        sleep=time.sleep,
    )


def crawl_racingjunk(source: dict, state: dict) -> list[dict]:
    """Scrape RacingJunk drag racing events. Returns structured text records (no flyers)."""
    return crawl_racingjunk_impl(
        source,
        state,
        fetch_page=fetch_page,
        headers=get_request_headers(source),
        delay_seconds=get_source_delay(source),
        max_pages=get_source_max_pages(source),
        sleep=time.sleep,
    )


def crawl_myracepass(source: dict, state: dict) -> list[dict]:
    """Scrape MyRacePass event listings from public HTML pages."""
    return crawl_myracepass_impl(source, state, fetch_page=fetch_page, headers=get_request_headers(source))


def parse_tmccc_page_events(html: str) -> list[dict]:
    """Extract and merge TMCCC calendar cards from one rendered page of HTML."""
    return parse_tmccc_page_events_impl(html)


def _tmccc_event_key(event: dict) -> str:
    return tmccc_event_key(event)


def _advance_tmccc_calendar(page, current_keys: list[str]) -> bool:
    """Click TMCCC's More Events control and wait for the visible event set to change."""
    return advance_tmccc_calendar_impl(page, current_keys)


def crawl_tmccc(source: dict, state: dict) -> list[dict]:
    """Scrape TMCCC event calendar (GoDaddy site builder)."""
    return crawl_tmccc_impl(
        source,
        state,
        headers=get_request_headers(source),
        parse_page_events=parse_tmccc_page_events,
        event_key=_tmccc_event_key,
        advance_calendar=_advance_tmccc_calendar,
    )


def crawl_rss(source: dict, state: dict) -> list[dict]:
    """Parse an RSS feed for event announcements."""
    return crawl_rss_impl(source, state, parse_feed=feedparser.parse)


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
        LOGGER.warning(f"  Unknown strategy '{strategy}', skipping.")
        return [], []
    result = fn(source, state)
    if not result:
        return [], []
    if isinstance(result[0], Path):
        return result, []
    return [], result


def _request_page(url: str, headers: dict[str, str]):
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response


def _request_image(url: str, headers: dict[str, str]):
    response = requests.get(url, headers=headers, timeout=15, stream=True)
    response.raise_for_status()
    return response


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
            "skipped": 0,
            "error": 0,
            "total_events": 0,
            "retries": get_retry_telemetry().get("claude", {}),
        }

    events = process.load_events()
    counts = {"new": 0, "merged": 0, "duplicate": 0, "skipped": 0, "error": 0}

    # Image flyers → Claude vision
    if downloaded:
        LOGGER.info("\nRunning vision extraction on new flyers...")
    for path in downloaded:
        LOGGER.info(f"\nProcessing: {path.name}")
        try:
            outcome, event = process.process_flyer(str(path), events)
            counts[outcome] += 1
            label = {"new": "NEW", "merged": "UPDATED", "duplicate": "SKIPPED", "skipped": "SKIPPED"}[outcome]
            LOGGER.info(f"  [{label}] {event.get('title', '?')} — {event.get('track', {}).get('name', '?')}")
            if "test-flyers" not in path.parts:
                path.unlink()
        except Exception as e:
            LOGGER.error(f"  [ERROR] {e}")
            counts["error"] += 1
            log_error("run_extraction.process_flyer", e, details={"flyer_path": path}, include_traceback=True)

    # Text listings → Claude text (haiku)
    if text_listings:
        LOGGER.info(f"\nParsing {len(text_listings)} text listings...")
    for listing in text_listings:
        title = listing.get("title", "?")
        LOGGER.info(f"\nParsing: {title}")
        try:
            if not is_in_scope_listing(listing):
                counts["skipped"] += 1
                LOGGER.info(f"  [SKIPPED] {title} — out of scope")
                continue

            extracted = extract_from_text(listing)
            if listing.get("source") == "TMCCC":
                extracted = enrich_tmccc_extracted_event(extracted, listing)

            if not is_in_scope_event(extracted):
                counts["skipped"] += 1
                LOGGER.info(f"  [SKIPPED] {title} — out of scope")
                continue

            if is_past_event(extracted):
                counts["skipped"] += 1
                LOGGER.info(f"  [SKIPPED] {title} — past event")
                continue

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
                LOGGER.info(f"  [UPDATED] {merged.get('title', '?')}")
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
                LOGGER.info(f"  [NEW] {new_event.get('title', '?')} — {new_event.get('track', {}).get('name', '?')}")
        except Exception as e:
            LOGGER.error(f"  [ERROR] {e}")
            counts["error"] += 1
            log_error(
                "run_extraction.extract_from_text",
                e,
                details={"listing_title": title, "source_url": listing.get("source_url", "")},
                include_traceback=True,
            )

    process.save_events(events)
    LOGGER.info(f"\n{len(events)} total events in database.")
    LOGGER.info(
        f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  "
        f"{counts['skipped']} skipped  |  {counts['error']} errors"
    )
    return {
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "image_flyers": len(downloaded),
        "text_listings": len(text_listings),
        "new": counts["new"],
        "merged": counts["merged"],
        "duplicate": counts["duplicate"],
        "skipped": counts["skipped"],
        "error": counts["error"],
        "total_events": len(events),
        "retries": get_retry_telemetry().get("claude", {}),
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
    reset_retry_telemetry()
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
            tracks = load_tracks_config()
            if track_filter:
                tracks = [t for t in tracks if track_filter in t["name"].lower()]
            LOGGER.info(f"=== Track websites ({len(tracks)}) ===")
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
            sources = load_sources_config()
            if source_filter:
                sources = [s for s in sources if source_filter in s["name"].lower()]
            LOGGER.info(f"\n=== Aggregator sources ({len(sources)}) ===")
            for source in sources:
                LOGGER.info(f"\n{source['name']}")
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

        LOGGER.info(f"\n{'─' * 50}")
        LOGGER.info(f"Crawl complete. {len(total_downloaded)} new flyer images, {len(total_text_listings)} text listings.")
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
        run_metrics["retries"] = get_retry_telemetry()
    except Exception as exc:
        run_metrics["status"] = "error"
        run_metrics["error"] = str(exc)
        run_metrics["retries"] = get_retry_telemetry()
        log_error("crawl.main", exc, details={"args": args}, include_traceback=True)
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        run_metrics["finished_at"] = finished_at.isoformat()
        run_metrics["elapsed_seconds"] = round(time.perf_counter() - started_perf, 2)
        if should_record_runtime_metrics():
            summary = record_run_metrics(run_metrics)
            LOGGER.info(f"\nRecorded crawl metrics in {METRICS_LOG}")
            LOGGER.info(f"Error log file: {ERROR_LOG}")
            if summary.get("average_seconds") is not None:
                LOGGER.info(
                    "Historical runtime: "
                    f"avg {format_duration(summary['average_seconds'])}, "
                    f"median {format_duration(summary['median_seconds'])}, "
                    f"last {format_duration(run_metrics['elapsed_seconds'])}"
                )


if __name__ == "__main__":
    main()

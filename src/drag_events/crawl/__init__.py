"""Crawl track websites and event aggregators for drag racing flyer images.

Two source types:
  src/drag_events/config/tracks.json   - individual track websites (generic image scraper)
  src/drag_events/config/sources.json  - aggregator sites with custom strategies per source

Usage:
    python -m drag_events.crawl                        # crawl all tracks + all sources
    python -m drag_events.crawl --tracks               # track websites only
    python -m drag_events.crawl --sources              # aggregator sources only
    python -m drag_events.crawl --track "Texas Motorplex"   # one track by name
    python -m drag_events.crawl --source "Bracketraces.com" # one source by name
"""

import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

from .. import flyer_processing
from ..core.logging_utils import get_logger
from ..core.paths import (
    BASE_DIR,
    CRAWL_ERROR_LOG_FILE,
    CRAWL_METRICS_LOG_FILE,
    CRAWL_METRICS_SUMMARY_FILE,
    CRAWL_STATE_FILE,
    DIST_DIR,
    FLYERS_DIR,
    RUNTIME_DIR,
    SOURCES_FILE,
    STATE_DIR,
    TRACKS_FILE,
    TRACING_DIR,
)
from ..core.retry_utils import execute_with_retries, get_retry_telemetry, reset_retry_telemetry
from ..events.dedup import find_same_event, merge_events, track_slug
from ..events.filters import is_in_scope_event, is_in_scope_listing, is_past_event
from ..events.tmccc import enrich_tmccc_extracted_event
from ..extraction.text import extract_from_text
from .collection import crawl_source_impl, crawl_track_impl
from .extraction import OUTCOME_LABELS, run_extraction_impl
from .http import (
    download_image_impl,
    fetch_page_impl,
    request_image_impl,
    request_page_impl,
)
from .run import run_crawl_cli
from .runtime import (
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
from .utils import (
    DEFAULT_HEADERS as HEADERS,
    ConfigValidationError,
    find_event_page_urls,
    get_image_links,
    get_request_headers,
    get_source_delay,
    get_source_max_pages,
    is_event_page,
    load_sources_config as _load_sources_config,
    load_tracks_config as _load_tracks_config,
    url_to_filename,
    validate_sources_config,
    validate_tracks_config,
)

CRAWL_STATE = CRAWL_STATE_FILE
METRICS_LOG = CRAWL_METRICS_LOG_FILE
METRICS_SUMMARY = CRAWL_METRICS_SUMMARY_FILE
ERROR_LOG = CRAWL_ERROR_LOG_FILE

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


def _legacy_runtime_files() -> list[tuple[Path, Path]]:
    return [
        (LEGACY_CRAWL_STATE, CRAWL_STATE),
        (LEGACY_METRICS_LOG, METRICS_LOG),
        (LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
        (LEGACY_ERROR_LOG, ERROR_LOG),
        (RUNTIME_LEGACY_METRICS_LOG, METRICS_LOG),
        (RUNTIME_LEGACY_METRICS_SUMMARY, METRICS_SUMMARY),
        (RUNTIME_LEGACY_ERROR_LOG, ERROR_LOG),
    ]


def _http_retry_options() -> dict:
    return {
        "execute_with_retries": execute_with_retries,
        "max_attempts": HTTP_MAX_ATTEMPTS,
        "base_delay_seconds": HTTP_RETRY_BASE_DELAY_SECONDS,
        "sleep": time.sleep,
        "logger": LOGGER,
        "log_error": log_error,
    }


def _source_request_options(source: dict) -> dict:
    return {"headers": get_request_headers(source), "sleep": time.sleep}


def _extraction_dependencies() -> dict:
    return {
        "perf_counter": time.perf_counter,
        "load_events": flyer_processing.load_events,
        "save_events": flyer_processing.save_events,
        "process_flyer": flyer_processing.process_flyer,
        "now": datetime.now,
        "timezone": timezone,
        "extract_from_text": extract_from_text,
        "enrich_tmccc_extracted_event": enrich_tmccc_extracted_event,
        "is_in_scope_listing": is_in_scope_listing,
        "is_in_scope_event": is_in_scope_event,
        "is_past_event": is_past_event,
        "find_same_event": find_same_event,
        "merge_events": merge_events,
        "track_slug": track_slug,
        "uuid4": uuid.uuid4,
        "get_retry_telemetry": get_retry_telemetry,
        "logger": LOGGER,
        "log_error": log_error,
    }


def _cli_dependencies() -> dict:
    return {
        "load_metric_entries": load_metric_entries,
        "summarize_metrics": summarize_metrics,
        "print_metrics_summary": print_metrics_summary,
        "reset_retry_telemetry": reset_retry_telemetry,
        "now": datetime.now,
        "timezone": timezone,
        "perf_counter": time.perf_counter,
        "load_state": load_state,
        "load_tracks_config": load_tracks_config,
        "load_sources_config": load_sources_config,
        "crawl_track": crawl_track,
        "crawl_source": crawl_source,
        "run_extraction": run_extraction,
        "save_state": save_state,
        "sleep": time.sleep,
        "get_retry_telemetry": get_retry_telemetry,
        "should_record_runtime_metrics": should_record_runtime_metrics,
        "record_run_metrics": record_run_metrics,
        "format_duration": format_duration,
        "metrics_log": METRICS_LOG,
        "error_log": ERROR_LOG,
        "logger": LOGGER,
        "log_error": log_error,
    }


def ensure_runtime_layout() -> None:
    ensure_runtime_layout_impl(RUNTIME_DIR, STATE_DIR, TRACING_DIR, _legacy_runtime_files())


def load_state() -> dict:
    return load_state_impl(CRAWL_STATE, ensure_runtime_layout=ensure_runtime_layout, json_loads=json.loads)


def save_state(state: dict) -> None:
    save_state_impl(CRAWL_STATE, state, ensure_runtime_layout=ensure_runtime_layout, json_dumps=json.dumps)


format_duration = _format_duration
summarize_metrics = _summarize_metrics


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


def log_error(
    context: str,
    error: Exception | str,
    *,
    error_log: Path | None = None,
    details: dict | None = None,
    include_traceback: bool = False,
) -> None:
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


def load_tracks_config(path: Path = TRACKS_FILE) -> list[dict]:
    return _load_tracks_config(path)


def load_sources_config(path: Path = SOURCES_FILE) -> list[dict]:
    return _load_sources_config(path)


def _request_page(url: str, headers: dict[str, str]):
    return request_page_impl(url, headers, requests_get=requests.get)


def _request_image(url: str, headers: dict[str, str]):
    return request_image_impl(url, headers, requests_get=requests.get)


def download_image(url: str, headers: dict[str, str] | None = None) -> Path | None:
    return download_image_impl(
        url,
        headers=headers or HEADERS,
        flyers_dir=FLYERS_DIR,
        default_headers=HEADERS,
        url_to_filename=url_to_filename,
        request_image=_request_image,
        **_http_retry_options(),
    )


def fetch_page(url: str, headers: dict[str, str] | None = None) -> BeautifulSoup | None:
    return fetch_page_impl(
        url,
        headers=headers or HEADERS,
        default_headers=HEADERS,
        request_page=_request_page,
        soup_parser=BeautifulSoup,
        **_http_retry_options(),
    )


def crawl_track(track: dict, state: dict) -> list[Path]:
    return crawl_track_impl(
        track,
        state,
        fetch_page=fetch_page,
        find_event_page_urls=find_event_page_urls,
        get_image_links=get_image_links,
        download_image=download_image,
        sleep=time.sleep,
        logger=LOGGER,
    )


def crawl_bracketraces(source: dict, state: dict) -> list[Path]:
    return crawl_bracketraces_impl(
        source,
        state,
        fetch_page=fetch_page,
        download_image=download_image,
        **_source_request_options(source),
        delay_seconds=get_source_delay(source),
    )


def crawl_racingjunk(source: dict, state: dict) -> list[dict]:
    return crawl_racingjunk_impl(
        source,
        state,
        fetch_page=fetch_page,
        **_source_request_options(source),
        delay_seconds=get_source_delay(source),
        max_pages=get_source_max_pages(source),
    )


def crawl_myracepass(source: dict, state: dict) -> list[dict]:
    return crawl_myracepass_impl(source, state, fetch_page=fetch_page, headers=get_request_headers(source))


parse_tmccc_page_events = parse_tmccc_page_events_impl
_tmccc_event_key = tmccc_event_key
_advance_tmccc_calendar = advance_tmccc_calendar_impl


def crawl_tmccc(source: dict, state: dict) -> list[dict]:
    return crawl_tmccc_impl(
        source,
        state,
        headers=get_request_headers(source),
        parse_page_events=parse_tmccc_page_events,
        event_key=_tmccc_event_key,
        advance_calendar=_advance_tmccc_calendar,
    )


def crawl_rss(source: dict, state: dict) -> list[dict]:
    return crawl_rss_impl(source, state, parse_feed=feedparser.parse)


STRATEGY_MAP = {
    "bracketraces": crawl_bracketraces,
    "racingjunk": crawl_racingjunk,
    "myracepass": crawl_myracepass,
    "tmccc": crawl_tmccc,
    "rss": crawl_rss,
}


def crawl_source(source: dict, state: dict) -> tuple[list[Path], list[dict]]:
    return crawl_source_impl(source, state, strategy_map=STRATEGY_MAP, logger=LOGGER)


def run_extraction(downloaded: list[Path], text_listings: list[dict]) -> dict:
    return run_extraction_impl(downloaded, text_listings, **_extraction_dependencies())


def main() -> None:
    run_crawl_cli(sys.argv[1:], **_cli_dependencies())

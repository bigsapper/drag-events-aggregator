"""Runtime state, metrics, and logging helpers for crawler execution."""

import json
import math
import os
import statistics
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .logging_utils import get_logger

LOGGER = get_logger(__name__)


def ensure_runtime_layout_impl(
    runtime_dir: Path,
    state_dir: Path,
    tracing_dir: Path,
    legacy_files: list[tuple[Path, Path]],
) -> None:
    runtime_dir.mkdir(exist_ok=True)
    state_dir.mkdir(exist_ok=True)
    tracing_dir.mkdir(exist_ok=True)
    for legacy, current in legacy_files:
        if legacy.exists() and not current.exists():
            current.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(current)


def load_state_impl(crawl_state: Path, *, ensure_runtime_layout, json_loads) -> dict:
    ensure_runtime_layout()
    if crawl_state.exists():
        return json_loads(crawl_state.read_text())
    return {"seen_urls": [], "racingjunk_events": [], "myracepass_events": [], "tmccc_events": []}


def save_state_impl(crawl_state: Path, state: dict, *, ensure_runtime_layout, json_dumps) -> None:
    ensure_runtime_layout()
    crawl_state.write_text(json_dumps(state, indent=2))


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


def load_metric_entries_impl(metrics_log: Path, *, ensure_runtime_layout) -> list[dict]:
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


def record_run_metrics_impl(
    run_metrics: dict,
    *,
    metrics_log: Path,
    summary_file: Path,
    ensure_runtime_layout,
    load_metric_entries,
    summarize_metrics,
) -> dict:
    ensure_runtime_layout()
    metrics_log.parent.mkdir(parents=True, exist_ok=True)
    with metrics_log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run_metrics) + "\n")

    entries = load_metric_entries(metrics_log)
    summary = summarize_metrics(entries)
    summary_file.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def should_record_runtime_metrics(env: dict | None = None) -> bool:
    environment = os.environ if env is None else env
    return "PYTEST_CURRENT_TEST" not in environment


def should_log_errors(details: dict | None = None, *, env: dict | None = None) -> bool:
    environment = os.environ if env is None else env
    if "PYTEST_CURRENT_TEST" in environment:
        return False
    if not details:
        return True

    for value in details.values():
        value_str = str(value)
        if "test-flyers" in value_str:
            return False
    return True


def get_error_log_path(error_log: Path) -> Path:
    return error_log


def log_error_impl(
    context: str,
    error: Exception | str,
    *,
    error_log: Path | None,
    details: dict | None,
    include_traceback: bool,
    should_log_errors,
    ensure_runtime_layout,
    get_error_log_path,
    traceback_format_exc,
) -> None:
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
            formatted_traceback = traceback_format_exc()
            fh.write(formatted_traceback)
            if not formatted_traceback.endswith("\n"):
                fh.write("\n")
        fh.write("\n")


def print_metrics_summary(summary: dict, *, format_duration) -> None:
    if not summary.get("recorded_runs"):
        LOGGER.info("No crawl metrics recorded yet.")
        return

    LOGGER.info("Crawl metrics summary")
    LOGGER.info(f"  recorded runs:   {summary['recorded_runs']}")
    LOGGER.info(f"  successful runs: {summary.get('successful_runs', 0)}")

    if summary.get("average_seconds") is not None:
        LOGGER.info(f"  average runtime: {format_duration(summary['average_seconds'])}")
        LOGGER.info(f"  median runtime:  {format_duration(summary['median_seconds'])}")
        LOGGER.info(f"  min runtime:     {format_duration(summary['min_seconds'])}")
        LOGGER.info(f"  max runtime:     {format_duration(summary['max_seconds'])}")
        if summary.get("p95_seconds") is not None:
            LOGGER.info(f"  p95 runtime:     {format_duration(summary['p95_seconds'])}")

    last_run = summary.get("last_run")
    if last_run:
        status = last_run.get("status", "unknown")
        started = last_run.get("started_at", "?")
        elapsed = format_duration(last_run.get("elapsed_seconds", 0))
        LOGGER.info(f"  last run:        {status} at {started} ({elapsed})")

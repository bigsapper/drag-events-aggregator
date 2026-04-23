"""CLI orchestration for crawl runs."""


def _filter_named_items(items: list[dict], name_filter: str | None) -> list[dict]:
    if not name_filter:
        return items
    return [item for item in items if name_filter in item["name"].lower()]


def _crawl_items(
    items: list[dict],
    *,
    perf_counter,
    crawl_item,
    summarize_result,
    save_state,
    state,
    sleep,
    log_item=None,
) -> tuple[list, list[dict]]:
    results = []
    metrics = []
    for item in items:
        if log_item is not None:
            log_item(item)
        item_start = perf_counter()
        result = crawl_item(item, state)
        elapsed = round(perf_counter() - item_start, 2)
        results.append(result)
        metrics.append(summarize_result(item, result, elapsed))
        save_state(state)
        sleep(1)
    return results, metrics


def run_crawl_cli(
    args: list[str],
    *,
    load_metric_entries,
    summarize_metrics,
    print_metrics_summary,
    reset_retry_telemetry,
    now,
    timezone,
    perf_counter,
    load_state,
    load_tracks_config,
    load_sources_config,
    crawl_track,
    crawl_source,
    run_extraction,
    save_state,
    sleep,
    get_retry_telemetry,
    should_record_runtime_metrics,
    record_run_metrics,
    format_duration,
    metrics_log,
    error_log,
    logger,
    log_error,
) -> None:
    if "--metrics" in args:
        print_metrics_summary(summarize_metrics(load_metric_entries()))
        return

    track_filter = None
    source_filter = None
    for i, arg in enumerate(args):
        if arg == "--track" and i + 1 < len(args):
            track_filter = args[i + 1].lower()
        if arg == "--source" and i + 1 < len(args):
            source_filter = args[i + 1].lower()

    run_tracks = "--sources" not in args and source_filter is None
    run_sources = "--tracks" not in args and track_filter is None
    reset_retry_telemetry()
    started_at = now(timezone.utc)
    started_perf = perf_counter()
    run_metrics = {
        "run_id": started_at.strftime("%Y%m%d-%H%M%S"),
        "started_at": started_at.isoformat(),
        "status": "success",
        "args": args,
        "filters": {"track": track_filter, "source": source_filter},
        "tracks": [],
        "sources": [],
    }

    tracks = []
    sources = []
    try:
        state = load_state()
        total_downloaded = []
        total_text_listings = []

        if run_tracks:
            tracks = _filter_named_items(load_tracks_config(), track_filter)
            logger.info(f"=== Track websites ({len(tracks)}) ===")
            track_results, run_metrics["tracks"] = _crawl_items(
                tracks,
                perf_counter=perf_counter,
                crawl_item=crawl_track,
                summarize_result=lambda track, files, elapsed: {
                    "name": track["name"],
                    "elapsed_seconds": elapsed,
                    "downloaded_images": len(files),
                },
                save_state=save_state,
                state=state,
                sleep=sleep,
            )
            for files in track_results:
                total_downloaded.extend(files)

        if run_sources:
            sources = _filter_named_items(load_sources_config(), source_filter)
            logger.info(f"\n=== Aggregator sources ({len(sources)}) ===")
            source_results, run_metrics["sources"] = _crawl_items(
                sources,
                perf_counter=perf_counter,
                crawl_item=crawl_source,
                summarize_result=lambda source, result, elapsed: {
                    "name": source["name"],
                    "strategy": source.get("strategy"),
                    "elapsed_seconds": elapsed,
                    "downloaded_images": len(result[0]),
                    "text_listings": len(result[1]),
                },
                save_state=save_state,
                state=state,
                sleep=sleep,
                log_item=lambda source: logger.info(f"\n{source['name']}"),
            )
            for files, listings in source_results:
                total_downloaded.extend(files)
                total_text_listings.extend(listings)

        logger.info(f"\n{'─' * 50}")
        logger.info(f"Crawl complete. {len(total_downloaded)} new flyer images, {len(total_text_listings)} text listings.")
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
        finished_at = now(timezone.utc)
        run_metrics["finished_at"] = finished_at.isoformat()
        run_metrics["elapsed_seconds"] = round(perf_counter() - started_perf, 2)
        if should_record_runtime_metrics():
            summary = record_run_metrics(run_metrics)
            logger.info(f"\nRecorded crawl metrics in {metrics_log}")
            logger.info(f"Error log file: {error_log}")
            if summary.get("average_seconds") is not None:
                logger.info(
                    "Historical runtime: "
                    f"avg {format_duration(summary['average_seconds'])}, "
                    f"median {format_duration(summary['median_seconds'])}, "
                    f"last {format_duration(run_metrics['elapsed_seconds'])}"
                )

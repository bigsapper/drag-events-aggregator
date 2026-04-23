"""Extraction pipeline helpers for crawled flyers and text listings."""

from pathlib import Path


OUTCOME_LABELS = {
    "new": "NEW",
    "merged": "UPDATED",
    "duplicate": "SKIPPED",
    "skipped": "SKIPPED",
}


def empty_outcome_counts() -> dict[str, int]:
    return {"new": 0, "merged": 0, "duplicate": 0, "skipped": 0, "error": 0}


def build_extraction_metrics(
    *,
    start: float,
    downloaded: list[Path],
    text_listings: list[dict],
    counts: dict[str, int],
    total_events: int,
    perf_counter,
    get_retry_telemetry,
) -> dict:
    return {
        "elapsed_seconds": round(perf_counter() - start, 2),
        "image_flyers": len(downloaded),
        "text_listings": len(text_listings),
        "new": counts["new"],
        "merged": counts["merged"],
        "duplicate": counts["duplicate"],
        "skipped": counts["skipped"],
        "error": counts["error"],
        "total_events": total_events,
        "retries": get_retry_telemetry().get("claude", {}),
    }


def log_flyer_processing_outcome(outcome: str, event: dict, *, logger) -> None:
    label = OUTCOME_LABELS[outcome]
    logger.info(f"  [{label}] {event.get('title', '?')} - {event.get('track', {}).get('name', '?')}")


def delete_processed_flyer(path: Path) -> None:
    if "test-flyers" not in path.parts:
        path.unlink()


def build_listing_flyer_entry(listing: dict, processed_at: str) -> dict:
    return {
        "file": listing.get("source_url", ""),
        "phash": None,
        "processed_at": processed_at,
    }


def replace_event(events: list[dict], event_id: str, updated_event: dict) -> None:
    idx = next(i for i, event in enumerate(events) if event["id"] == event_id)
    events[idx] = updated_event


def build_new_text_event(extracted: dict, listing: dict, processed_at: str, *, track_slug, uuid4) -> dict:
    track = extracted.get("track") or {}
    extracted["track"] = {
        "id": track_slug(track.get("name"), track.get("state")),
        "name": track.get("name"),
        "city": track.get("city"),
        "state": track.get("state"),
    }
    return {
        "id": str(uuid4()),
        **extracted,
        "flyers": [build_listing_flyer_entry(listing, processed_at)],
        "created_at": processed_at,
        "updated_at": processed_at,
    }


def merge_text_listing_event(
    events: list[dict],
    same_event: dict,
    extracted: dict,
    listing: dict,
    processed_at: str,
    *,
    merge_events,
) -> dict:
    merged = merge_events(same_event, extracted, build_listing_flyer_entry(listing, processed_at))
    merged["updated_at"] = processed_at
    replace_event(events, same_event["id"], merged)
    return merged


def upsert_text_listing_event(
    listing: dict,
    extracted: dict,
    events: list[dict],
    *,
    now,
    timezone,
    find_same_event,
    merge_events,
    track_slug,
    uuid4,
) -> tuple[str, dict]:
    processed_at = now(timezone.utc).isoformat()
    same_event = find_same_event(extracted, events)
    if same_event:
        return "merged", merge_text_listing_event(
            events,
            same_event,
            extracted,
            listing,
            processed_at,
            merge_events=merge_events,
        )

    new_event = build_new_text_event(extracted, listing, processed_at, track_slug=track_slug, uuid4=uuid4)
    events.append(new_event)
    return "new", new_event


def extract_listing_event(
    listing: dict,
    *,
    is_in_scope_listing,
    extract_from_text,
    enrich_tmccc_extracted_event,
    is_in_scope_event,
    is_past_event,
    logger,
) -> dict | None:
    title = listing.get("title", "?")
    if not is_in_scope_listing(listing):
        logger.info(f"  [SKIPPED] {title} - out of scope")
        return None

    extracted = extract_from_text(listing)
    if listing.get("source") == "TMCCC":
        extracted = enrich_tmccc_extracted_event(extracted, listing)

    if not is_in_scope_event(extracted):
        logger.info(f"  [SKIPPED] {title} - out of scope")
        return None

    if is_past_event(extracted):
        logger.info(f"  [SKIPPED] {title} - past event")
        return None

    return extracted


def process_downloaded_flyers(
    downloaded: list[Path],
    events: list[dict],
    counts: dict[str, int],
    *,
    process_flyer,
    logger,
    log_error,
) -> None:
    if downloaded:
        logger.info("\nRunning vision extraction on new flyers...")

    for path in downloaded:
        logger.info(f"\nProcessing: {path.name}")
        try:
            outcome, event = process_flyer(str(path), events)
            counts[outcome] += 1
            log_flyer_processing_outcome(outcome, event, logger=logger)
            delete_processed_flyer(path)
        except Exception as exc:
            logger.error(f"  [ERROR] {exc}")
            counts["error"] += 1
            log_error("run_extraction.process_flyer", exc, details={"flyer_path": path}, include_traceback=True)


def process_text_listings(
    text_listings: list[dict],
    events: list[dict],
    counts: dict[str, int],
    *,
    now,
    timezone,
    extract_from_text,
    enrich_tmccc_extracted_event,
    is_in_scope_listing,
    is_in_scope_event,
    is_past_event,
    find_same_event,
    merge_events,
    track_slug,
    uuid4,
    logger,
    log_error,
) -> None:
    if text_listings:
        logger.info(f"\nParsing {len(text_listings)} text listings...")

    for listing in text_listings:
        title = listing.get("title", "?")
        logger.info(f"\nParsing: {title}")
        try:
            extracted = extract_listing_event(
                listing,
                is_in_scope_listing=is_in_scope_listing,
                extract_from_text=extract_from_text,
                enrich_tmccc_extracted_event=enrich_tmccc_extracted_event,
                is_in_scope_event=is_in_scope_event,
                is_past_event=is_past_event,
                logger=logger,
            )
            if extracted is None:
                counts["skipped"] += 1
                continue

            outcome, event = upsert_text_listing_event(
                listing,
                extracted,
                events,
                now=now,
                timezone=timezone,
                find_same_event=find_same_event,
                merge_events=merge_events,
                track_slug=track_slug,
                uuid4=uuid4,
            )
            counts[outcome] += 1
            if outcome == "merged":
                logger.info(f"  [UPDATED] {event.get('title', '?')}")
            else:
                logger.info(f"  [NEW] {event.get('title', '?')} - {event.get('track', {}).get('name', '?')}")
        except Exception as exc:
            logger.error(f"  [ERROR] {exc}")
            counts["error"] += 1
            log_error(
                "run_extraction.extract_from_text",
                exc,
                details={"listing_title": title, "source_url": listing.get("source_url", "")},
                include_traceback=True,
            )


def run_extraction_impl(
    downloaded: list[Path],
    text_listings: list[dict],
    *,
    perf_counter,
    load_events,
    save_events,
    process_flyer,
    now,
    timezone,
    extract_from_text,
    enrich_tmccc_extracted_event,
    is_in_scope_listing,
    is_in_scope_event,
    is_past_event,
    find_same_event,
    merge_events,
    track_slug,
    uuid4,
    get_retry_telemetry,
    logger,
    log_error,
) -> dict:
    start = perf_counter()
    if not downloaded and not text_listings:
        return build_extraction_metrics(
            start=start,
            downloaded=[],
            text_listings=[],
            counts=empty_outcome_counts(),
            total_events=0,
            perf_counter=perf_counter,
            get_retry_telemetry=get_retry_telemetry,
        )

    events = load_events()
    counts = empty_outcome_counts()

    process_downloaded_flyers(
        downloaded,
        events,
        counts,
        process_flyer=process_flyer,
        logger=logger,
        log_error=log_error,
    )
    process_text_listings(
        text_listings,
        events,
        counts,
        now=now,
        timezone=timezone,
        extract_from_text=extract_from_text,
        enrich_tmccc_extracted_event=enrich_tmccc_extracted_event,
        is_in_scope_listing=is_in_scope_listing,
        is_in_scope_event=is_in_scope_event,
        is_past_event=is_past_event,
        find_same_event=find_same_event,
        merge_events=merge_events,
        track_slug=track_slug,
        uuid4=uuid4,
        logger=logger,
        log_error=log_error,
    )

    save_events(events)
    logger.info(f"\n{len(events)} total events in database.")
    logger.info(
        f"  {counts['new']} new  |  {counts['merged']} updated  |  {counts['duplicate']} duplicate  |  "
        f"{counts['skipped']} skipped  |  {counts['error']} errors"
    )
    return build_extraction_metrics(
        start=start,
        downloaded=downloaded,
        text_listings=text_listings,
        counts=counts,
        total_events=len(events),
        perf_counter=perf_counter,
        get_retry_telemetry=get_retry_telemetry,
    )

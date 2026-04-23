"""Helpers for enriching TMCCC event listings and extracted events."""

from __future__ import annotations

import re

TMCCC_CLASSES = [
    "Stock Muscle",
    "Street Muscle",
    "King Muscle",
    "EV Muscle",
    "Competition Muscle",
    "Modified Muscle",
    "Electronics",
    "Pro Muscle",
    "Super Pro Muscle",
    "CA$H Bracket",
]

_CITY_STATE_RE = re.compile(
    r"(?P<city>[A-Za-z][A-Za-z .'-]+?)\s*,?\s+(?P<state>[A-Z]{2})\s+\d{5}(?:-\d{4})?$"
)


def parse_tmccc_description(description: str | None) -> dict[str, str | list[str] | None]:
    """Extract structured fields from the TMCCC event detail text."""
    phone = None
    website = None
    notes: list[str] = []

    for raw_line in (description or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("track phone:"):
            phone = line.split(":", 1)[1].strip() or None
            continue
        if line.lower().startswith("website:"):
            website = line.split(":", 1)[1].strip() or None
            continue

        cleaned = line.strip("* ").strip()
        if cleaned:
            notes.append(cleaned)

    return {"phone": phone, "website": website, "notes": notes}


def parse_tmccc_city_state(location_text: str | None) -> tuple[str | None, str | None]:
    """Parse city/state from the TMCCC address line."""
    if not location_text:
        return None, None

    compact = " ".join(location_text.split())
    match = _CITY_STATE_RE.search(compact)
    if not match:
        return None, None
    return match.group("city").strip(), match.group("state").strip()


def enrich_tmccc_extracted_event(event: dict, listing: dict) -> dict:
    """Fill TMCCC fields directly from structured listing data."""
    enriched = {**event}
    track = {**(enriched.get("track") or {})}
    contact = {**(enriched.get("contact") or {})}

    location_text = listing.get("location_text")
    city, state = parse_tmccc_city_state(location_text)
    if city and not track.get("city"):
        track["city"] = city
    if state and not track.get("state"):
        track["state"] = state
    if track:
        enriched["track"] = track

    details = parse_tmccc_description(listing.get("description"))
    if details["phone"] and not contact.get("phone"):
        contact["phone"] = details["phone"]
    if details["website"] and not contact.get("website"):
        contact["website"] = details["website"]
    if contact:
        enriched["contact"] = contact

    if not enriched.get("series"):
        enriched["series"] = "TMCCC"
    if not enriched.get("classes"):
        enriched["classes"] = list(TMCCC_CLASSES)

    existing_notes = (enriched.get("notes") or "").strip()
    note_parts: list[str] = [existing_notes] if existing_notes else []
    for item in details["notes"] or []:
        if item not in note_parts:
            note_parts.append(item)
    enriched["notes"] = "\n".join(note_parts) if note_parts else None
    return enriched

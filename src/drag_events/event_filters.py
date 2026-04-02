"""Shared event-scope and freshness filters."""

from datetime import date


OUT_OF_SCOPE_TITLE_KEYWORDS = (
    "banquet",
)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_past_event(event: dict, *, today: date | None = None) -> bool:
    today = today or date.today()
    dates = event.get("dates", {}) if isinstance(event.get("dates"), dict) else {}
    end_date = _parse_date(dates.get("end")) or _parse_date(dates.get("start"))
    if not end_date:
        return False
    return end_date < today


def is_in_scope_title(title: str | None) -> bool:
    if not title:
        return True
    normalized = title.strip().lower()
    return not any(keyword in normalized for keyword in OUT_OF_SCOPE_TITLE_KEYWORDS)


def is_in_scope_event(event: dict) -> bool:
    return is_in_scope_title(event.get("title"))


def is_in_scope_listing(listing: dict) -> bool:
    return is_in_scope_title(listing.get("title"))

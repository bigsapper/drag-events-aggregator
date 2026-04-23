from datetime import date

from drag_events.events import filters as event_filters


def test_is_past_event_uses_end_date_when_present():
    event = {"dates": {"start": "2026-03-01", "end": "2026-03-03"}}
    assert event_filters.is_past_event(event, today=date(2026, 3, 4)) is True


def test_is_past_event_returns_false_for_missing_date():
    assert event_filters.is_past_event({}, today=date(2026, 4, 1)) is False


def test_is_past_event_returns_false_for_invalid_date():
    event = {"dates": {"start": "not-a-date"}}
    assert event_filters.is_past_event(event, today=date(2026, 4, 1)) is False


def test_is_in_scope_title_rejects_banquet():
    assert event_filters.is_in_scope_title("2026 TMCCC Banquet") is False


def test_is_in_scope_title_allows_regular_event():
    assert event_filters.is_in_scope_title("Funny Car Chaos Classic") is True


def test_is_in_scope_title_allows_missing_title():
    assert event_filters.is_in_scope_title(None) is True


def test_is_in_scope_event_uses_title():
    assert event_filters.is_in_scope_event({"title": "2026 TMCCC Banquet"}) is False


def test_is_in_scope_listing_uses_title():
    assert event_filters.is_in_scope_listing({"title": "2026 TMCCC Banquet"}) is False

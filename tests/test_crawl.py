"""Tests for crawl.py — web crawling and extraction orchestration."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from bs4 import BeautifulSoup

import drag_events.crawl as crawl
from tests.conftest import make_1x1_png

PROJECT_DIR = Path(__file__).parent.parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_response(text="", content=b"", content_type="text/html", raise_for_status=False):
    resp = MagicMock()
    resp.text = text
    resp.content = content
    resp.headers = {"content-type": content_type}
    if raise_for_status:
        resp.raise_for_status.side_effect = Exception("HTTP Error")
    else:
        resp.raise_for_status.return_value = None
    return resp


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ── State management ──────────────────────────────────────────────────────────

def test_load_state_missing_file(tmp_crawl_state):
    state = crawl.load_state()
    assert state["seen_urls"] == []
    assert "racingjunk_events" in state
    assert "myracepass_events" in state


def test_load_state_existing(tmp_crawl_state):
    data = {"seen_urls": ["http://a.com"], "racingjunk_events": [], "myracepass_events": []}
    tmp_crawl_state.write_text(json.dumps(data))
    assert crawl.load_state()["seen_urls"] == ["http://a.com"]


def test_save_state_roundtrip(tmp_crawl_state):
    state = {"seen_urls": ["http://b.com"], "racingjunk_events": ["Race A"], "myracepass_events": []}
    crawl.save_state(state)
    assert crawl.load_state() == state


def test_validate_tracks_config_rejects_missing_required_fields():
    with pytest.raises(crawl.ConfigValidationError, match=r"tracks\[0\]\.url"):
        crawl.validate_tracks_config([{"name": "Track", "state": "TX"}])


def test_validate_tracks_config_rejects_non_list():
    with pytest.raises(crawl.ConfigValidationError, match="tracks config must be a list of objects"):
        crawl.validate_tracks_config({"name": "Track"})


def test_validate_tracks_config_rejects_non_object_entry():
    with pytest.raises(crawl.ConfigValidationError, match=r"tracks\[0\] must be an object"):
        crawl.validate_tracks_config(["not-a-track"])


def test_validate_tracks_config_rejects_blank_name():
    with pytest.raises(crawl.ConfigValidationError, match=r"tracks\[0\]\.name"):
        crawl.validate_tracks_config([{"name": " ", "state": "TX", "url": "https://example.com"}])


def test_validate_tracks_config_rejects_lowercase_state():
    with pytest.raises(crawl.ConfigValidationError, match=r"tracks\[0\]\.state"):
        crawl.validate_tracks_config([{"name": "Track", "state": "tx", "url": "https://example.com"}])


def test_validate_tracks_config_accepts_valid_entries():
    data = [{"name": "Track", "state": "TX", "url": "https://example.com"}]
    assert crawl.validate_tracks_config(data) == data


def test_validate_tracks_config_rejects_non_boolean_enabled():
    with pytest.raises(crawl.ConfigValidationError, match=r"tracks\[0\]\.enabled"):
        crawl.validate_tracks_config(
            [{"name": "Track", "state": "TX", "url": "https://example.com", "enabled": "yes"}]
        )


def test_validate_sources_config_rejects_non_list():
    with pytest.raises(crawl.ConfigValidationError, match="sources config must be a list of objects"):
        crawl.validate_sources_config({"name": "Source"})


def test_validate_sources_config_rejects_non_object_entry():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\] must be an object"):
        crawl.validate_sources_config(["not-a-source"])


def test_validate_sources_config_rejects_blank_name():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\]\.name"):
        crawl.validate_sources_config([{"name": "", "url": "https://example.com", "strategy": "rss"}])


def test_validate_sources_config_rejects_invalid_url():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\]\.url"):
        crawl.validate_sources_config([{"name": "Source", "url": "ftp://example.com", "strategy": "rss"}])


def test_validate_sources_config_rejects_unknown_strategy():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\]\.strategy"):
        crawl.validate_sources_config([{"name": "Source", "url": "https://example.com", "strategy": "unknown"}])


def test_validate_sources_config_rejects_missing_bracketraces_event_pages():
    with pytest.raises(crawl.ConfigValidationError, match=r"event_pages"):
        crawl.validate_sources_config([{"name": "Bracketraces", "url": "https://example.com", "strategy": "bracketraces"}])


def test_validate_sources_config_rejects_invalid_bracketraces_event_page_entries():
    with pytest.raises(crawl.ConfigValidationError, match=r"event_pages entries"):
        crawl.validate_sources_config(
            [{"name": "Bracketraces", "url": "https://example.com", "strategy": "bracketraces", "event_pages": ["events"]}]
        )


def test_validate_sources_config_rejects_invalid_racingjunk_drag_racing_url():
    with pytest.raises(crawl.ConfigValidationError, match=r"drag_racing_url"):
        crawl.validate_sources_config(
            [{"name": "RacingJunk", "url": "https://example.com", "strategy": "racingjunk", "drag_racing_url": "ftp://example.com"}]
        )


def test_validate_sources_config_accepts_valid_entries():
    data = [{"name": "Source", "url": "https://example.com", "strategy": "rss"}]
    assert crawl.validate_sources_config(data) == data


def test_validate_sources_config_rejects_non_boolean_enabled():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\]\.enabled"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "enabled": 1}]
        )


def test_validate_sources_config_rejects_non_object_request_headers():
    with pytest.raises(crawl.ConfigValidationError, match=r"sources\[0\]\.request_headers"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "request_headers": "not-a-dict"}]
        )


def test_validate_sources_config_rejects_non_string_request_header_value():
    with pytest.raises(crawl.ConfigValidationError, match=r"request_headers values must be strings"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "request_headers": {"X-Test": 1}}]
        )


def test_validate_sources_config_rejects_blank_request_header_key():
    with pytest.raises(crawl.ConfigValidationError, match=r"request_headers keys must be non-empty strings"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "request_headers": {"": "value"}}]
        )


def test_validate_sources_config_rejects_negative_page_delay_seconds():
    with pytest.raises(crawl.ConfigValidationError, match=r"page_delay_seconds"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "page_delay_seconds": -0.5}]
        )


def test_validate_sources_config_rejects_invalid_max_pages():
    with pytest.raises(crawl.ConfigValidationError, match=r"max_pages"):
        crawl.validate_sources_config(
            [{"name": "Source", "url": "https://example.com", "strategy": "rss", "max_pages": 0}]
        )


def test_load_tracks_config_rejects_invalid_json(tmp_path):
    path = tmp_path / "tracks.json"
    path.write_text("{not-json")
    with pytest.raises(crawl.ConfigValidationError, match="Invalid JSON"):
        crawl.load_tracks_config(path)


def test_load_tracks_config_filters_disabled_entries(tmp_path):
    path = tmp_path / "tracks.json"
    path.write_text(
        json.dumps(
            [
                {"name": "Track A", "state": "TX", "url": "https://a.example.com"},
                {"name": "Track B", "state": "OK", "url": "https://b.example.com", "enabled": False},
            ]
        )
    )
    assert crawl.load_tracks_config(path) == [
        {"name": "Track A", "state": "TX", "url": "https://a.example.com"}
    ]


def test_load_sources_config_filters_disabled_entries(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {"name": "Source A", "url": "https://a.example.com", "strategy": "rss"},
                {"name": "Source B", "url": "https://b.example.com", "strategy": "rss", "enabled": False},
            ]
        )
    )
    assert crawl.load_sources_config(path) == [
        {"name": "Source A", "url": "https://a.example.com", "strategy": "rss"}
    ]


def test_load_sources_config_accepts_per_site_settings(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "Source A",
                    "url": "https://a.example.com",
                    "strategy": "racingjunk",
                    "request_headers": {"X-Test": "true"},
                    "page_delay_seconds": 1.25,
                    "max_pages": 3,
                }
            ]
        )
    )
    assert crawl.load_sources_config(path) == [
        {
            "name": "Source A",
            "url": "https://a.example.com",
            "strategy": "racingjunk",
            "request_headers": {"X-Test": "true"},
            "page_delay_seconds": 1.25,
            "max_pages": 3,
        }
    ]


# ── Shared helpers ────────────────────────────────────────────────────────────

def test_is_event_page_keyword_in_url():
    assert crawl.is_event_page("http://track.com/schedule", "") is True


def test_is_event_page_keyword_in_text():
    assert crawl.is_event_page("http://track.com/page", "Upcoming Race Events") is True


def test_is_event_page_no_match():
    assert crawl.is_event_page("http://track.com/about", "Contact Us") is False


def test_get_image_links_finds_src():
    html = '<img src="flyer.jpg" width="600" height="600">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert any("flyer.jpg" in u for u in links)


def test_get_image_links_finds_data_src():
    html = '<img data-src="flyer.png" width="600" height="600">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert any("flyer.png" in u for u in links)


def test_get_image_links_skips_small_images():
    html = '<img src="icon.jpg" width="50" height="50">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert links == []


def test_get_image_links_skips_unsupported_extension():
    html = '<img src="logo.svg">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert links == []


def test_get_image_links_no_src_skipped():
    html = '<img alt="no src here">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert links == []


def test_find_event_page_urls_same_domain():
    html = '<a href="/schedule">Schedule</a>'
    urls = crawl.find_event_page_urls(_soup(html), "http://track.com", "http://track.com")
    assert any("schedule" in u for u in urls)


def test_find_event_page_urls_external_filtered():
    html = '<a href="http://other.com/events">Events</a>'
    urls = crawl.find_event_page_urls(_soup(html), "http://track.com", "http://track.com")
    assert urls == []


def test_url_to_filename_deterministic():
    url = "http://track.com/flyers/spring-race.jpg"
    assert crawl.url_to_filename(url) == crawl.url_to_filename(url)


def test_url_to_filename_no_extension_defaults_jpg():
    url = "http://track.com/flyers/spring-race"
    assert crawl.url_to_filename(url).endswith(".jpg")


def test_url_to_filename_includes_hash():
    url = "http://track.com/flyers/race.jpg"
    name = crawl.url_to_filename(url)
    # format: slug-hash.ext — hash is 8 hex chars before extension
    stem = Path(name).stem
    assert len(stem.split("-")[-1]) == 8


def test_get_request_headers_merges_source_headers():
    headers = crawl.get_request_headers({"request_headers": {"X-Test": "true", "User-Agent": "CustomBot/1.0"}})
    assert headers["X-Test"] == "true"
    assert headers["User-Agent"] == "CustomBot/1.0"


def test_get_source_delay_uses_defaults_and_override():
    assert crawl.get_source_delay({"strategy": "racingjunk"}) == 0.75
    assert crawl.get_source_delay({"strategy": "rss"}, default=0.2) == 0.2
    assert crawl.get_source_delay({"strategy": "racingjunk", "page_delay_seconds": 1.5}) == 1.5


def test_get_source_max_pages_uses_defaults_and_override():
    assert crawl.get_source_max_pages({"strategy": "racingjunk"}) == 10
    assert crawl.get_source_max_pages({"strategy": "rss"}, default=2) == 2
    assert crawl.get_source_max_pages({"strategy": "racingjunk", "max_pages": 4}) == 4


# ── download_image ────────────────────────────────────────────────────────────

def test_download_image_skips_existing(tmp_flyers_dir):
    url = "http://track.com/flyer.jpg"
    dest = tmp_flyers_dir / crawl.url_to_filename(url)
    dest.write_bytes(b"existing")
    with patch("drag_events.crawl.requests.get") as mock_get:
        result = crawl.download_image(url)
    assert result is None
    mock_get.assert_not_called()


def test_download_image_success(tmp_flyers_dir):
    url = "http://track.com/newflyer.jpg"
    resp = _mock_response(content=b"\xff\xd8\xff", content_type="image/jpeg")
    with patch("drag_events.crawl.requests.get", return_value=resp):
        result = crawl.download_image(url)
    assert result is not None
    assert result.exists()


def test_download_image_non_image_content_type(tmp_flyers_dir):
    url = "http://track.com/page.jpg"
    resp = _mock_response(content=b"<html>", content_type="text/html")
    with patch("drag_events.crawl.requests.get", return_value=resp):
        result = crawl.download_image(url)
    assert result is None


def test_download_image_request_exception(tmp_flyers_dir, capsys):
    url = "http://track.com/broken.jpg"
    with patch("drag_events.crawl.requests.get", side_effect=Exception("timeout")), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.download_image(url)
    assert result is None
    assert "Download failed" in capsys.readouterr().out


def test_download_image_retries_transient_request_failure(tmp_flyers_dir):
    url = "http://track.com/retry.jpg"
    resp = _mock_response(content=b"\xff\xd8\xff", content_type="image/jpeg")
    with patch("drag_events.crawl.requests.get", side_effect=[Exception("timeout"), resp]) as mock_get, \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        result = crawl.download_image(url)
    assert result is not None
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1.0)


# ── fetch_page ────────────────────────────────────────────────────────────────

def test_fetch_page_returns_soup():
    resp = _mock_response(text="<html><body>Hello</body></html>")
    with patch("drag_events.crawl.requests.get", return_value=resp):
        soup = crawl.fetch_page("http://track.com")
    assert soup is not None
    assert soup.find("body") is not None


def test_fetch_page_http_error_returns_none(capsys):
    resp = _mock_response(raise_for_status=True)
    with patch("drag_events.crawl.requests.get", return_value=resp), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.fetch_page("http://track.com")
    assert result is None


def test_fetch_page_connection_error_returns_none(capsys):
    with patch("drag_events.crawl.requests.get", side_effect=Exception("connection refused")), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.fetch_page("http://track.com")
    assert result is None
    assert "Could not fetch" in capsys.readouterr().out


def test_fetch_page_retries_transient_request_failure():
    resp = _mock_response(text="<html><body>Hello</body></html>")
    with patch("drag_events.crawl.requests.get", side_effect=[Exception("timeout"), resp]) as mock_get, \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        result = crawl.fetch_page("http://track.com")
    assert result is not None
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1.0)


def test_fetch_page_uses_custom_headers():
    resp = _mock_response(text="<html><body>Hello</body></html>")
    headers = {"User-Agent": "CustomBot/1.0", "X-Test": "true"}
    with patch("drag_events.crawl.requests.get", return_value=resp) as mock_get:
        crawl.fetch_page("http://track.com", headers=headers)
    assert mock_get.call_args.kwargs["headers"] == headers


# ── crawl_track ───────────────────────────────────────────────────────────────

def test_crawl_track_no_new_images():
    state = {"seen_urls": ["http://track.com/flyer.jpg"]}
    html = '<img src="/flyer.jpg" width="600" height="600">'
    resp = _mock_response(text=html)
    with patch("drag_events.crawl.requests.get", return_value=resp), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_track({"name": "Test Track", "url": "http://track.com"}, state)
    assert result == []


def test_crawl_track_downloads_new_image(tmp_flyers_dir):
    state = {"seen_urls": []}
    home_html = '<a href="/schedule">Schedule</a>'
    page_html = '<img src="/flyer.jpg" width="600" height="600">'
    img_resp = _mock_response(content=b"\xff\xd8\xff", content_type="image/jpeg")

    def side_effect(url, **kwargs):
        if "flyer.jpg" in url:
            return img_resp
        if "schedule" in url:
            return _mock_response(text=page_html)
        return _mock_response(text=home_html)

    with patch("drag_events.crawl.requests.get", side_effect=side_effect), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_track({"name": "Test Track", "url": "http://track.com"}, state)
    assert len(result) == 1


# ── crawl_bracketraces ────────────────────────────────────────────────────────

def test_crawl_bracketraces_downloads_flyer(tmp_flyers_dir):
    state = {"seen_urls": []}
    html = '<img src="/spring-fling.webp" width="800" height="600">'
    img_resp = _mock_response(content=b"WEBP", content_type="image/webp")

    def side_effect(url, **kwargs):
        if ".webp" in url:
            return img_resp
        return _mock_response(text=html)

    source = {"url": "http://bracketraces.com", "event_pages": ["/event-spring-fling.php"]}
    with patch("drag_events.crawl.requests.get", side_effect=side_effect), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_bracketraces(source, state)
    assert len(result) == 1


def test_crawl_bracketraces_finds_flyer_anchor(tmp_flyers_dir):
    state = {"seen_urls": []}
    html = '<a href="/spring-flyer.jpg">Download Flyer</a>'
    img_resp = _mock_response(content=b"\xff\xd8\xff", content_type="image/jpeg")

    def side_effect(url, **kwargs):
        if ".jpg" in url:
            return img_resp
        return _mock_response(text=html)

    source = {"url": "http://bracketraces.com", "event_pages": ["/event.php"]}
    with patch("drag_events.crawl.requests.get", side_effect=side_effect), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_bracketraces(source, state)
    assert len(result) == 1


def test_crawl_bracketraces_skips_fetch_failure():
    state = {"seen_urls": []}
    source = {"url": "http://bracketraces.com", "event_pages": ["/event.php"]}
    with patch("drag_events.crawl.requests.get", side_effect=Exception("timeout")), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_bracketraces(source, state)
    assert result == []


def test_crawl_bracketraces_uses_request_headers_and_configured_delay(tmp_flyers_dir):
    state = {"seen_urls": []}
    html = '<img src="/spring-fling.webp" width="800" height="600">'
    img_resp = _mock_response(content=b"WEBP", content_type="image/webp")

    def side_effect(url, **kwargs):
        assert kwargs["headers"]["X-Test"] == "true"
        if ".webp" in url:
            return img_resp
        return _mock_response(text=html)

    source = {
        "url": "http://bracketraces.com",
        "event_pages": ["/event-spring-fling.php"],
        "request_headers": {"X-Test": "true"},
        "page_delay_seconds": 1.25,
    }
    with patch("drag_events.crawl.requests.get", side_effect=side_effect), \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        result = crawl.crawl_bracketraces(source, state)
    assert len(result) == 1
    mock_sleep.assert_called_once_with(1.25)


# ── crawl_racingjunk ──────────────────────────────────────────────────────────

_RJ_HTML = """
<html><body>
  <div class="event-listing">
    <h3>Summer Bracket Race</h3>
    <div class="date">June 14, 2026</div>
    <div class="location">Tulsa, OK</div>
    <a href="/events/123">Details</a>
  </div>
</body></html>
"""


def test_crawl_racingjunk_new_events():
    state = {"seen_urls": [], "racingjunk_events": []}
    page1 = _mock_response(text=_RJ_HTML)
    page2 = _mock_response(text="<html><body></body></html>")

    with patch("drag_events.crawl.requests.get", side_effect=[page1, page2]), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com/events", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert len(result) == 1
    assert result[0]["title"] == "Summer Bracket Race"
    assert result[0]["source"] == "RacingJunk"


def test_crawl_racingjunk_skips_known_titles():
    state = {"seen_urls": [], "racingjunk_events": ["Summer Bracket Race"]}
    with patch("drag_events.crawl.requests.get", return_value=_mock_response(text=_RJ_HTML)), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert result == []


def test_crawl_racingjunk_stops_on_empty_page():
    state = {"seen_urls": [], "racingjunk_events": []}
    empty = _mock_response(text="<html><body></body></html>")
    with patch("drag_events.crawl.requests.get", return_value=empty), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert result == []


def test_crawl_racingjunk_honors_max_pages_and_delay():
    state = {"seen_urls": [], "racingjunk_events": []}
    page_one = _mock_response(text=_RJ_HTML.replace("Summer Bracket Race", "Race One"))
    page_two = _mock_response(text=_RJ_HTML.replace("Summer Bracket Race", "Race Two"))

    with patch("drag_events.crawl.requests.get", side_effect=[page_one, page_two]) as mock_get, \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        result = crawl.crawl_racingjunk(
            {
                "url": "http://racingjunk.com/events",
                "drag_racing_url": "http://racingjunk.com/drag",
                "max_pages": 2,
                "page_delay_seconds": 1.5,
                "request_headers": {"X-Test": "true"},
            },
            state,
        )
    assert len(result) == 2
    assert mock_get.call_count == 2
    assert all(call.kwargs["headers"]["X-Test"] == "true" for call in mock_get.call_args_list)
    assert mock_sleep.call_count == 2
    assert all(mock_call == call(1.5) for mock_call in mock_sleep.call_args_list)


# ── crawl_myracepass ──────────────────────────────────────────────────────────

_MRP_HTML = """
<html><body>
  <div class="event-card">
    <h3>Friday Night Drags</h3>
    <div class="date">July 4, 2026</div>
    <div class="type">Bracket</div>
    <a href="/events/456">Info</a>
  </div>
</body></html>
"""


def test_crawl_myracepass_new_events():
    state = {"seen_urls": [], "myracepass_events": []}
    with patch("drag_events.crawl.requests.get", return_value=_mock_response(text=_MRP_HTML)):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert len(result) == 1
    assert result[0]["title"] == "Friday Night Drags"


def test_crawl_myracepass_skips_known():
    state = {"seen_urls": [], "myracepass_events": ["Friday Night Drags"]}
    with patch("drag_events.crawl.requests.get", return_value=_mock_response(text=_MRP_HTML)):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert result == []


def test_crawl_myracepass_fetch_failure():
    state = {"seen_urls": [], "myracepass_events": []}
    with patch("drag_events.crawl.requests.get", side_effect=Exception("timeout")), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert result == []


# ── crawl_tmccc ──────────────────────────────────────────────────────────────

def test_parse_tmccc_page_events_merges_summary_and_detail_cards():
    html = """
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">4/12/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #2 Thunder Valley Raceway Park</div>
      <div data-aid="CALENDAR_EVENT_TIME">
        <h4>8am</h4><h4>-</h4><h4>4pm</h4>
        <p>10500 48th St., Lexington, OK 73051</p>
      </div>
    </div>
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">4/12/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #2 Thunder Valley Raceway Park</div>
      <div data-aid="CALENDAR_DESC_TEXT">1/4 Mile\n4 Points 1st Round</div>
    </div>
    """

    events = crawl.parse_tmccc_page_events(html)

    assert len(events) == 1
    assert events[0]["title"] == "Race #2 Thunder Valley Raceway Park"
    assert events[0]["time_text"] == "8am - 4pm"
    assert events[0]["location_text"] == "10500 48th St., Lexington, OK 73051"
    assert events[0]["description"] == "1/4 Mile\n4 Points 1st Round"


def test_crawl_tmccc_pages_until_button_is_disabled(monkeypatch):
    page_html = [
        """
        <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
          <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
          <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park</div>
        </div>
        """,
        """
        <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
          <div data-aid="CALENDAR_EVENT_DATE">4/12/2026</div>
          <div data-aid="CALENDAR_EVENT_TITLE">Race #2 Thunder Valley Raceway Park</div>
        </div>
        """,
    ]

    class FakeLocator:
        def __init__(self, page):
            self.page = page
            self.first = self

        def count(self):
            return 1

        def is_visible(self):
            return True

        def is_disabled(self):
            return self.page.index >= len(page_html) - 1

        def scroll_into_view_if_needed(self):
            return None

        def click(self):
            if self.page.index < len(page_html) - 1:
                self.page.index += 1

    class FakePage:
        def __init__(self):
            self.index = 0

        def goto(self, *args, **kwargs):
            return None

        def wait_for_selector(self, *args, **kwargs):
            return None

        def wait_for_function(self, *args, **kwargs):
            return None

        def content(self):
            return page_html[self.index]

        def locator(self, selector):
            assert selector == "[data-aid='CALENDAR_SHOW_NEXT_EVENTS']"
            return FakeLocator(self)

    class FakeBrowser:
        def new_page(self, **kwargs):
            return FakePage()

        def close(self):
            return None

    class FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless=True, **kwargs):
                return FakeBrowser()

    class FakeContextManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTimeoutError(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(
            sync_playwright=lambda: FakeContextManager(),
            TimeoutError=FakeTimeoutError,
        ),
    )

    state = {"seen_urls": [], "racingjunk_events": [], "myracepass_events": [], "tmccc_events": []}
    result = crawl.crawl_tmccc({"url": "http://tmccc.test/events"}, state)

    assert [item["title"] for item in result] == [
        "Race #1 Xtreme Raceway Park",
        "Race #2 Thunder Valley Raceway Park",
    ]
    assert state["tmccc_events"] == [
        "Race #1 Xtreme Raceway Park|3/22/2026",
        "Race #2 Thunder Valley Raceway Park|4/12/2026",
    ]


def test_parse_tmccc_page_events_skips_card_missing_date_or_title():
    """Cards without both a date and title are silently skipped (line 304)."""
    html = """
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_TITLE">No Date Card</div>
    </div>
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
    </div>
    """
    assert crawl.parse_tmccc_page_events(html) == []


def test_parse_tmccc_page_events_skips_card_with_empty_title():
    """Cards where title text resolves to empty are skipped (line 309)."""
    html = """
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">   </div>
    </div>
    """
    assert crawl.parse_tmccc_page_events(html) == []


def _make_tmccc_playwright_mock(page_html, monkeypatch, *, timeout_on_advance=False):
    """Build and install a fake playwright module for TMCCC tests."""

    class FakeLocator:
        def __init__(self, page):
            self.page = page
            self.first = self

        def count(self):
            return 1

        def is_visible(self):
            return True

        def is_disabled(self):
            return self.page.index >= len(page_html) - 1

        def scroll_into_view_if_needed(self):
            return None

        def click(self):
            if self.page.index < len(page_html) - 1:
                self.page.index += 1

    class FakePage:
        def __init__(self):
            self.index = 0

        def goto(self, *args, **kwargs):
            return None

        def wait_for_selector(self, *args, **kwargs):
            return None

        def wait_for_function(self, *args, **kwargs):
            if timeout_on_advance:
                raise FakeTimeoutError("timeout")

        def content(self):
            return page_html[self.index]

        def locator(self, selector):
            assert selector == "[data-aid='CALENDAR_SHOW_NEXT_EVENTS']"
            return FakeLocator(self)

    class FakeBrowser:
        def new_page(self, **kwargs):
            return FakePage()

        def close(self):
            return None

    class FakePlaywright:
        class chromium:
            @staticmethod
            def launch(headless=True, **kwargs):
                return FakeBrowser()

    class FakeContextManager:
        def __enter__(self):
            return FakePlaywright()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTimeoutError(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        types.SimpleNamespace(
            sync_playwright=lambda: FakeContextManager(),
            TimeoutError=FakeTimeoutError,
        ),
    )


def test_crawl_tmccc_skips_already_seen_events(monkeypatch):
    """Events already in state['tmccc_events'] are not returned again (line 423)."""
    page_html = [
        """
        <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
          <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
          <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park</div>
        </div>
        """
    ]
    _make_tmccc_playwright_mock(page_html, monkeypatch)
    state = {"tmccc_events": ["Race #1 Xtreme Raceway Park|3/22/2026"]}
    result = crawl.crawl_tmccc({"url": "http://tmccc.test/events"}, state)
    assert result == []


def test_crawl_tmccc_timeout_on_advance_stops_gracefully(monkeypatch):
    """A PlaywrightTimeoutError from wait_for_function exits the loop cleanly (line 414)."""
    page_html = [
        """
        <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
          <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
          <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park</div>
        </div>
        """,
        """
        <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
          <div data-aid="CALENDAR_EVENT_DATE">4/12/2026</div>
          <div data-aid="CALENDAR_EVENT_TITLE">Race #2 Thunder Valley Raceway Park</div>
        </div>
        """,
    ]
    _make_tmccc_playwright_mock(page_html, monkeypatch, timeout_on_advance=True)
    state = {"tmccc_events": []}
    result = crawl.crawl_tmccc({"url": "http://tmccc.test/events"}, state)
    # First page was scraped before the timeout; second page was never reached
    assert len(result) == 1
    assert result[0]["title"] == "Race #1 Xtreme Raceway Park"


def test_advance_tmccc_calendar_returns_false_when_no_next_button():
    """Returns False immediately when CALENDAR_SHOW_NEXT_EVENTS is absent (line 350)."""
    class FakeLocator:
        first = None
        def count(self):
            return 0

    class FakePage:
        def locator(self, selector):
            return FakeLocator()

    assert crawl._advance_tmccc_calendar(FakePage(), ["some|key"]) is False


def test_advance_tmccc_calendar_returns_false_when_button_not_visible():
    """Returns False when the next button exists but is not visible (line 354)."""
    class FakeLocator:
        first = None

        def __init__(self):
            self.first = self

        def count(self):
            return 1

        def is_visible(self):
            return False

    class FakePage:
        def locator(self, selector):
            return FakeLocator()

    assert crawl._advance_tmccc_calendar(FakePage(), ["some|key"]) is False


def test_advance_tmccc_calendar_empty_keys_uses_wait_for_selector():
    """When current_keys is empty, falls back to wait_for_selector after clicking (line 380)."""
    waited = []

    class FakeLocator:
        first = None

        def __init__(self):
            self.first = self

        def count(self):
            return 1

        def is_visible(self):
            return True

        def is_disabled(self):
            return False

        def scroll_into_view_if_needed(self):
            pass

        def click(self):
            pass

    class FakePage:
        def locator(self, selector):
            return FakeLocator()

        def wait_for_selector(self, selector, **kwargs):
            waited.append(selector)

        def wait_for_function(self, *args, **kwargs):
            raise AssertionError("should not be called")

    result = crawl._advance_tmccc_calendar(FakePage(), [])
    assert result is True
    assert waited == ["[data-aid='CALENDAR_EVENT_TITLE']"]


# ── crawl_rss ─────────────────────────────────────────────────────────────────

def _mock_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def test_crawl_rss_new_items():
    state = {"seen_urls": [], "racingjunk_events": [], "myracepass_events": []}
    entry = {"link": "http://site.com/event/1", "title": "Race Day", "published": "2026-06-01", "summary": "Fun race"}
    with patch("drag_events.crawl.feedparser.parse", return_value=_mock_feed([entry])):
        result = crawl.crawl_rss({"url": "http://site.com/feed.rss", "name": "TestFeed"}, state)
    assert len(result) == 1
    assert result[0]["title"] == "Race Day"
    assert result[0]["source"] == "TestFeed"


def test_crawl_rss_skips_seen_urls():
    state = {"seen_urls": ["http://site.com/event/1"], "racingjunk_events": [], "myracepass_events": []}
    entry = {"link": "http://site.com/event/1", "title": "Race Day", "published": "2026-06-01", "summary": ""}
    with patch("drag_events.crawl.feedparser.parse", return_value=_mock_feed([entry])):
        result = crawl.crawl_rss({"url": "http://site.com/feed.rss", "name": "TestFeed"}, state)
    assert result == []


def test_crawl_rss_empty_feed():
    state = {"seen_urls": []}
    with patch("drag_events.crawl.feedparser.parse", return_value=_mock_feed([])):
        result = crawl.crawl_rss({"url": "http://site.com/feed.rss", "name": "TestFeed"}, state)
    assert result == []


# ── crawl_source ──────────────────────────────────────────────────────────────

def test_crawl_source_unknown_strategy(capsys):
    source = {"name": "Unknown", "strategy": "nonexistent", "url": "http://x.com"}
    state = {}
    images, listings = crawl.crawl_source(source, state)
    assert images == []
    assert listings == []
    assert "Unknown strategy" in capsys.readouterr().out


def test_crawl_source_non_string_strategy(capsys):
    source = {"name": "Broken", "strategy": None, "url": "http://x.com"}
    state = {}
    images, listings = crawl.crawl_source(source, state)
    assert images == []
    assert listings == []
    assert "Invalid strategy" in capsys.readouterr().out


def test_crawl_source_empty_result():
    source = {"name": "Test", "strategy": "bracketraces", "url": "http://x.com", "event_pages": []}
    state = {"seen_urls": []}
    with patch("drag_events.crawl.time.sleep"):
        images, listings = crawl.crawl_source(source, state)
    assert images == []
    assert listings == []


def test_crawl_source_image_strategy_returns_in_first_slot(tmp_flyers_dir):
    # STRATEGY_MAP holds direct function references captured at import time;
    # patch the map entry, not the module-level name.
    source = {"name": "Test", "strategy": "bracketraces", "url": "http://x.com", "event_pages": []}
    state = {"seen_urls": []}
    fake_path = tmp_flyers_dir / "flyer.jpg"
    fake_path.write_bytes(b"img")
    mock_fn = MagicMock(return_value=[fake_path])
    with patch.dict(crawl.STRATEGY_MAP, {"bracketraces": mock_fn}):
        images, listings = crawl.crawl_source(source, state)
    assert images == [fake_path]
    assert listings == []


def test_crawl_source_text_strategy_returns_in_second_slot():
    source = {"name": "RJ", "strategy": "racingjunk", "url": "http://rj.com"}
    state = {"seen_urls": [], "racingjunk_events": []}
    listing = {"title": "Race", "source": "RacingJunk"}
    mock_fn = MagicMock(return_value=[listing])
    with patch.dict(crawl.STRATEGY_MAP, {"racingjunk": mock_fn}):
        images, listings = crawl.crawl_source(source, state)
    assert images == []
    assert listings == [listing]


# ── run_extraction ────────────────────────────────────────────────────────────

def test_run_extraction_noop_on_empty_input(tmp_events_file):
    with patch("drag_events.crawl.flyer_processing.load_events") as mock_load:
        result = crawl.run_extraction([], [])
    mock_load.assert_not_called()
    assert result["skipped"] == 0


def test_run_extraction_image_new_event(tmp_path, tmp_events_file, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.flyer_processing.process_flyer", return_value=("new", sample_extracted)), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        crawl.run_extraction([img], [])
    mock_save.assert_called_once()
    assert not img.exists()  # file deleted after successful processing


def test_run_extraction_image_error_keeps_file(tmp_path, tmp_events_file):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.flyer_processing.process_flyer", side_effect=RuntimeError("boom")), \
         patch("drag_events.crawl.flyer_processing.save_events"):
        crawl.run_extraction([img], [])
    assert img.exists()  # kept on error


def test_run_extraction_text_new_event(tmp_events_file):
    listing = {"title": "Race Day", "source_url": "http://rj.com/1", "source": "RacingJunk"}
    extracted = {
        "title": "Race Day", "event_type": "bracket",
        "track": {"name": "Tulsa Raceway Park", "state": "OK"},
        "dates": {"start": "2026-06-01"}, "confidence": 0.8,
    }
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text", return_value=extracted), \
         patch("drag_events.crawl.find_same_event", return_value=None), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        crawl.run_extraction([], [listing])
    mock_save.assert_called_once()
    saved_events = mock_save.call_args[0][0]
    assert len(saved_events) == 1
    assert saved_events[0]["title"] == "Race Day"


def test_run_extraction_text_new_tmccc_event_applies_enrichment(tmp_events_file):
    listing = {
        "title": "Race #2 Thunder Valley Raceway Park",
        "source_url": "https://tmccc.org/events",
        "source": "TMCCC",
        "location_text": "10500 48th St., Lexington, OK 73051",
        "description": "Track Phone: 405-413-1522\nWebsite: https://www.thundervalleyracewaypark.com\n*1/4 Mile*",
    }
    extracted = {
        "title": "Race #2 Thunder Valley Raceway Park",
        "event_type": "points_race",
        "track": {"name": "Thunder Valley Raceway Park", "city": None, "state": None},
        "dates": {"start": "2026-05-12"},
        "confidence": 0.65,
    }
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text", return_value=extracted), \
         patch("drag_events.crawl.find_same_event", return_value=None), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        crawl.run_extraction([], [listing])
    saved_events = mock_save.call_args[0][0]
    assert saved_events[0]["track"]["city"] == "Lexington"
    assert saved_events[0]["track"]["state"] == "OK"
    assert saved_events[0]["contact"]["phone"] == "405-413-1522"
    assert "Super Pro Muscle" in saved_events[0]["classes"]


def test_run_extraction_text_merged_event(tmp_events_file, sample_events, sample_extracted):
    listing = {"title": "Spring Bracket Classic", "source_url": "http://rj.com/2", "source": "RacingJunk"}
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=sample_events), \
         patch("drag_events.crawl.extract_from_text", return_value=sample_extracted), \
         patch("drag_events.crawl.find_same_event", return_value=sample_events[0]), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        crawl.run_extraction([], [listing])
    saved = mock_save.call_args[0][0]
    assert len(saved[0]["flyers"]) == 2  # original + new


def test_run_extraction_text_error_continues(tmp_events_file, capsys):
    listing = {"title": "Bad Event", "source_url": "", "source": "RJ"}
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text", side_effect=RuntimeError("Claude error")), \
         patch("drag_events.crawl.flyer_processing.save_events"):
        crawl.run_extraction([], [listing])
    assert "ERROR" in capsys.readouterr().out


def test_run_extraction_text_skips_out_of_scope_listing(tmp_events_file):
    listing = {"title": "2026 TMCCC Banquet", "source_url": "http://tmccc.org/events", "source": "TMCCC"}
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text") as mock_extract, \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        result = crawl.run_extraction([], [listing])
    mock_extract.assert_not_called()
    mock_save.assert_called_once_with([])
    assert result["skipped"] == 1


def test_run_extraction_text_skips_past_event(tmp_events_file):
    listing = {"title": "Race Day", "source_url": "http://rj.com/1", "source": "RacingJunk"}
    extracted = {
        "title": "Race Day",
        "event_type": "bracket",
        "track": {"name": "Tulsa Raceway Park", "state": "OK"},
        "dates": {"start": "2025-06-01"},
        "confidence": 0.8,
    }
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text", return_value=extracted), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        result = crawl.run_extraction([], [listing])
    mock_save.assert_called_once_with([])
    assert result["skipped"] == 1


def test_run_extraction_text_skips_out_of_scope_extracted_event(tmp_events_file):
    listing = {"title": "Race Day", "source_url": "http://tmccc.org/events", "source": "TMCCC"}
    extracted = {
        "title": "2026 TMCCC Banquet",
        "event_type": "unknown",
        "track": {"name": None, "state": None},
        "dates": {"start": "2026-12-05"},
        "confidence": 0.3,
    }
    with patch("drag_events.crawl.flyer_processing.load_events", return_value=[]), \
         patch("drag_events.crawl.extract_from_text", return_value=extracted), \
         patch("drag_events.crawl.flyer_processing.save_events") as mock_save:
        result = crawl.run_extraction([], [listing])
    mock_save.assert_called_once_with([])
    assert result["skipped"] == 1


# ── main() ────────────────────────────────────────────────────────────────────

def test_main_runs_all_by_default(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py"]), \
         patch("drag_events.crawl.load_tracks_config", return_value=[]), \
         patch("drag_events.crawl.load_sources_config", return_value=[]), \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state"), \
         patch("drag_events.crawl.time.sleep"):
        crawl.main()


def test_main_tracks_only(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py", "--tracks"]), \
         patch("drag_events.crawl.load_tracks_config", return_value=[]), \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state"), \
         patch("drag_events.crawl.time.sleep"):
        crawl.main()


def test_main_sources_only(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py", "--sources"]), \
         patch("drag_events.crawl.load_sources_config", return_value=[]), \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state"), \
         patch("drag_events.crawl.time.sleep"):
        crawl.main()


def test_main_track_filter(tmp_crawl_state):
    """--track NAME filters to matching tracks and iterates over them."""
    tracks = [{"name": "Texas Motorplex", "url": "http://a.com"},
              {"name": "Tulsa Raceway Park", "url": "http://b.com"}]
    with patch.object(sys, "argv", ["crawl.py", "--track", "texas"]), \
         patch("drag_events.crawl.load_tracks_config", return_value=tracks), \
         patch("drag_events.crawl.crawl_track", return_value=[]) as mock_ct, \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state"), \
         patch("drag_events.crawl.time.sleep"):
        crawl.main()
    # Only Texas Motorplex matches "texas"
    assert mock_ct.call_count == 1
    assert mock_ct.call_args[0][0]["name"] == "Texas Motorplex"


def test_main_source_filter(tmp_crawl_state):
    """--source NAME filters to matching sources and iterates over them."""
    sources = [{"name": "Bracketraces.com", "strategy": "bracketraces", "url": "http://a.com", "event_pages": []},
               {"name": "RacingJunk Events", "strategy": "racingjunk", "url": "http://b.com", "drag_racing_url": "http://b.com/drag"}]
    with patch.object(sys, "argv", ["crawl.py", "--source", "bracketraces"]), \
         patch("drag_events.crawl.load_sources_config", return_value=sources), \
         patch("drag_events.crawl.crawl_source", return_value=([], [])) as mock_cs, \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state"), \
         patch("drag_events.crawl.time.sleep"):
        crawl.main()
    assert mock_cs.call_count == 1
    assert mock_cs.call_args[0][0]["name"] == "Bracketraces.com"


def test_main_iterates_tracks_and_saves_state(tmp_crawl_state):
    """Crawling multiple tracks calls save_state and sleep after each one."""
    tracks = [{"name": "Track A", "url": "http://a.com"},
              {"name": "Track B", "url": "http://b.com"}]
    with patch.object(sys, "argv", ["crawl.py", "--tracks"]), \
         patch("drag_events.crawl.load_tracks_config", return_value=tracks), \
         patch("drag_events.crawl.crawl_track", return_value=[]) as mock_ct, \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state") as mock_ss, \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        crawl.main()
    assert mock_ct.call_count == 2
    assert mock_ss.call_count == 2
    assert mock_sleep.call_count == 2


def test_main_iterates_sources_and_saves_state(tmp_crawl_state):
    """Crawling multiple sources calls save_state and sleep after each one."""
    sources = [
        {"name": "Source A", "strategy": "bracketraces", "url": "http://a.com", "event_pages": []},
        {"name": "Source B", "strategy": "bracketraces", "url": "http://b.com", "event_pages": []},
    ]
    with patch.object(sys, "argv", ["crawl.py", "--sources"]), \
         patch("drag_events.crawl.load_sources_config", return_value=sources), \
         patch("drag_events.crawl.crawl_source", return_value=([], [])) as mock_cs, \
         patch("drag_events.crawl.run_extraction"), \
         patch("drag_events.crawl.save_state") as mock_ss, \
         patch("drag_events.crawl.time.sleep") as mock_sleep:
        crawl.main()
    assert mock_cs.call_count == 2
    assert mock_ss.call_count == 2
    assert mock_sleep.call_count == 2


def test_main_fails_fast_on_invalid_tracks_config(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py", "--tracks"]), \
         patch("drag_events.crawl.load_tracks_config", side_effect=crawl.ConfigValidationError("bad tracks config")), \
         patch("drag_events.crawl.should_record_runtime_metrics", return_value=False), \
         patch("drag_events.crawl.record_run_metrics", return_value={}), \
         patch("drag_events.crawl.log_error") as mock_log, \
         patch("drag_events.crawl.time.sleep"):
        with pytest.raises(crawl.ConfigValidationError, match="bad tracks config"):
            crawl.main()

    mock_log.assert_called_once()


# ── Previously uncovered edge cases ──────────────────────────────────────────

def test_get_image_links_invalid_dimension_attribute():
    """width/height attributes with non-numeric values should not raise."""
    html = '<img src="flyer.jpg" width="auto" height="auto">'
    links = crawl.get_image_links(_soup(html), "http://track.com")
    assert any("flyer.jpg" in u for u in links)


def test_crawl_track_returns_empty_when_homepage_unreachable():
    """If fetch_page returns None for the homepage, crawl_track returns []."""
    state = {"seen_urls": []}
    with patch("drag_events.crawl.fetch_page", return_value=None):
        result = crawl.crawl_track({"name": "Dead Track", "url": "http://dead.com"}, state)
    assert result == []


def test_crawl_racingjunk_breaks_on_fetch_none():
    """If fetch_page returns None mid-pagination, the loop stops cleanly."""
    state = {"seen_urls": [], "racingjunk_events": []}
    with patch("drag_events.crawl.fetch_page", return_value=None), \
         patch("drag_events.crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://rj.com", "drag_racing_url": "http://rj.com/drag"},
            state,
        )
    assert result == []

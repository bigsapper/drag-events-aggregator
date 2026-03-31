"""Tests for crawl.py — web crawling and extraction orchestration."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
from bs4 import BeautifulSoup

import crawl
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


# ── download_image ────────────────────────────────────────────────────────────

def test_download_image_skips_existing(tmp_flyers_dir):
    url = "http://track.com/flyer.jpg"
    dest = tmp_flyers_dir / crawl.url_to_filename(url)
    dest.write_bytes(b"existing")
    with patch("crawl.requests.get") as mock_get:
        result = crawl.download_image(url)
    assert result is None
    mock_get.assert_not_called()


def test_download_image_success(tmp_flyers_dir):
    url = "http://track.com/newflyer.jpg"
    resp = _mock_response(content=b"\xff\xd8\xff", content_type="image/jpeg")
    with patch("crawl.requests.get", return_value=resp):
        result = crawl.download_image(url)
    assert result is not None
    assert result.exists()


def test_download_image_non_image_content_type(tmp_flyers_dir):
    url = "http://track.com/page.jpg"
    resp = _mock_response(content=b"<html>", content_type="text/html")
    with patch("crawl.requests.get", return_value=resp):
        result = crawl.download_image(url)
    assert result is None


def test_download_image_request_exception(tmp_flyers_dir, capsys):
    url = "http://track.com/broken.jpg"
    with patch("crawl.requests.get", side_effect=Exception("timeout")):
        result = crawl.download_image(url)
    assert result is None
    assert "Download failed" in capsys.readouterr().out


# ── fetch_page ────────────────────────────────────────────────────────────────

def test_fetch_page_returns_soup():
    resp = _mock_response(text="<html><body>Hello</body></html>")
    with patch("crawl.requests.get", return_value=resp):
        soup = crawl.fetch_page("http://track.com")
    assert soup is not None
    assert soup.find("body") is not None


def test_fetch_page_http_error_returns_none(capsys):
    resp = _mock_response(raise_for_status=True)
    with patch("crawl.requests.get", return_value=resp):
        result = crawl.fetch_page("http://track.com")
    assert result is None


def test_fetch_page_connection_error_returns_none(capsys):
    with patch("crawl.requests.get", side_effect=Exception("connection refused")):
        result = crawl.fetch_page("http://track.com")
    assert result is None
    assert "Could not fetch" in capsys.readouterr().out


# ── crawl_track ───────────────────────────────────────────────────────────────

def test_crawl_track_no_new_images():
    state = {"seen_urls": ["http://track.com/flyer.jpg"]}
    html = '<img src="/flyer.jpg" width="600" height="600">'
    resp = _mock_response(text=html)
    with patch("crawl.requests.get", return_value=resp), \
         patch("crawl.time.sleep"):
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

    with patch("crawl.requests.get", side_effect=side_effect), \
         patch("crawl.time.sleep"):
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
    with patch("crawl.requests.get", side_effect=side_effect), \
         patch("crawl.time.sleep"):
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
    with patch("crawl.requests.get", side_effect=side_effect), \
         patch("crawl.time.sleep"):
        result = crawl.crawl_bracketraces(source, state)
    assert len(result) == 1


def test_crawl_bracketraces_skips_fetch_failure():
    state = {"seen_urls": []}
    source = {"url": "http://bracketraces.com", "event_pages": ["/event.php"]}
    with patch("crawl.requests.get", side_effect=Exception("timeout")), \
         patch("crawl.time.sleep"):
        result = crawl.crawl_bracketraces(source, state)
    assert result == []


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

    with patch("crawl.requests.get", side_effect=[page1, page2]), \
         patch("crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com/events", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert len(result) == 1
    assert result[0]["title"] == "Summer Bracket Race"
    assert result[0]["source"] == "RacingJunk"


def test_crawl_racingjunk_skips_known_titles():
    state = {"seen_urls": [], "racingjunk_events": ["Summer Bracket Race"]}
    with patch("crawl.requests.get", return_value=_mock_response(text=_RJ_HTML)), \
         patch("crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert result == []


def test_crawl_racingjunk_stops_on_empty_page():
    state = {"seen_urls": [], "racingjunk_events": []}
    empty = _mock_response(text="<html><body></body></html>")
    with patch("crawl.requests.get", return_value=empty), \
         patch("crawl.time.sleep"):
        result = crawl.crawl_racingjunk(
            {"url": "http://racingjunk.com", "drag_racing_url": "http://racingjunk.com/drag"},
            state,
        )
    assert result == []


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
    with patch("crawl.requests.get", return_value=_mock_response(text=_MRP_HTML)):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert len(result) == 1
    assert result[0]["title"] == "Friday Night Drags"


def test_crawl_myracepass_skips_known():
    state = {"seen_urls": [], "myracepass_events": ["Friday Night Drags"]}
    with patch("crawl.requests.get", return_value=_mock_response(text=_MRP_HTML)):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert result == []


def test_crawl_myracepass_fetch_failure():
    state = {"seen_urls": [], "myracepass_events": []}
    with patch("crawl.requests.get", side_effect=Exception("timeout")):
        result = crawl.crawl_myracepass({"url": "http://myracepass.com/events"}, state)
    assert result == []


# ── crawl_rss ─────────────────────────────────────────────────────────────────

def _mock_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


def test_crawl_rss_new_items():
    state = {"seen_urls": [], "racingjunk_events": [], "myracepass_events": []}
    entry = {"link": "http://site.com/event/1", "title": "Race Day", "published": "2026-06-01", "summary": "Fun race"}
    with patch("crawl.feedparser.parse", return_value=_mock_feed([entry])):
        result = crawl.crawl_rss({"url": "http://site.com/feed.rss", "name": "TestFeed"}, state)
    assert len(result) == 1
    assert result[0]["title"] == "Race Day"
    assert result[0]["source"] == "TestFeed"


def test_crawl_rss_skips_seen_urls():
    state = {"seen_urls": ["http://site.com/event/1"], "racingjunk_events": [], "myracepass_events": []}
    entry = {"link": "http://site.com/event/1", "title": "Race Day", "published": "2026-06-01", "summary": ""}
    with patch("crawl.feedparser.parse", return_value=_mock_feed([entry])):
        result = crawl.crawl_rss({"url": "http://site.com/feed.rss", "name": "TestFeed"}, state)
    assert result == []


def test_crawl_rss_empty_feed():
    state = {"seen_urls": []}
    with patch("crawl.feedparser.parse", return_value=_mock_feed([])):
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


def test_crawl_source_empty_result():
    source = {"name": "Test", "strategy": "bracketraces", "url": "http://x.com", "event_pages": []}
    state = {"seen_urls": []}
    with patch("crawl.time.sleep"):
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
    with patch("crawl.process.load_events") as mock_load:
        crawl.run_extraction([], [])
    mock_load.assert_not_called()


def test_run_extraction_image_new_event(tmp_path, tmp_events_file, sample_extracted):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("crawl.process.load_events", return_value=[]), \
         patch("crawl.process.process_flyer", return_value=("new", sample_extracted)), \
         patch("crawl.process.save_events") as mock_save:
        crawl.run_extraction([img], [])
    mock_save.assert_called_once()
    assert not img.exists()  # file deleted after successful processing


def test_run_extraction_image_error_keeps_file(tmp_path, tmp_events_file):
    img = make_1x1_png(tmp_path / "flyer.jpg")
    with patch("crawl.process.load_events", return_value=[]), \
         patch("crawl.process.process_flyer", side_effect=RuntimeError("boom")), \
         patch("crawl.process.save_events"):
        crawl.run_extraction([img], [])
    assert img.exists()  # kept on error


def test_run_extraction_text_new_event(tmp_events_file):
    listing = {"title": "Race Day", "source_url": "http://rj.com/1", "source": "RacingJunk"}
    extracted = {
        "title": "Race Day", "event_type": "bracket",
        "track": {"name": "Tulsa Raceway Park", "state": "OK"},
        "dates": {"start": "2026-06-01"}, "confidence": 0.8,
    }
    with patch("crawl.process.load_events", return_value=[]), \
         patch("crawl.extract_from_text", return_value=extracted), \
         patch("crawl.find_same_event", return_value=None), \
         patch("crawl.process.save_events") as mock_save:
        crawl.run_extraction([], [listing])
    mock_save.assert_called_once()
    saved_events = mock_save.call_args[0][0]
    assert len(saved_events) == 1
    assert saved_events[0]["title"] == "Race Day"


def test_run_extraction_text_merged_event(tmp_events_file, sample_events, sample_extracted):
    listing = {"title": "Spring Bracket Classic", "source_url": "http://rj.com/2", "source": "RacingJunk"}
    with patch("crawl.process.load_events", return_value=sample_events), \
         patch("crawl.extract_from_text", return_value=sample_extracted), \
         patch("crawl.find_same_event", return_value=sample_events[0]), \
         patch("crawl.process.save_events") as mock_save:
        crawl.run_extraction([], [listing])
    saved = mock_save.call_args[0][0]
    assert len(saved[0]["flyers"]) == 2  # original + new


def test_run_extraction_text_error_continues(tmp_events_file, capsys):
    listing = {"title": "Bad Event", "source_url": "", "source": "RJ"}
    with patch("crawl.process.load_events", return_value=[]), \
         patch("crawl.extract_from_text", side_effect=RuntimeError("Claude error")), \
         patch("crawl.process.save_events"):
        crawl.run_extraction([], [listing])
    assert "ERROR" in capsys.readouterr().out


# ── main() ────────────────────────────────────────────────────────────────────

def test_main_runs_all_by_default(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py"]), \
         patch("crawl.json.loads", return_value=[]), \
         patch("crawl.run_extraction"), \
         patch("crawl.save_state"), \
         patch("crawl.time.sleep"):
        crawl.main()


def test_main_tracks_only(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py", "--tracks"]), \
         patch("crawl.json.loads", return_value=[]), \
         patch("crawl.run_extraction"), \
         patch("crawl.save_state"), \
         patch("crawl.time.sleep"):
        crawl.main()


def test_main_sources_only(tmp_crawl_state):
    with patch.object(sys, "argv", ["crawl.py", "--sources"]), \
         patch("crawl.json.loads", return_value=[]), \
         patch("crawl.run_extraction"), \
         patch("crawl.save_state"), \
         patch("crawl.time.sleep"):
        crawl.main()

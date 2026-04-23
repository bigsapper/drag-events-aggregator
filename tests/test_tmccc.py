from drag_events.crawl.strategies.tmccc import parse_tmccc_page_events_impl
from drag_events.tmccc_enrichment import enrich_tmccc_extracted_event, parse_tmccc_city_state, parse_tmccc_description


def test_parse_tmccc_page_events_skips_banquet_titles():
    html = """
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">12/5/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">2026 TMCCC Banquet</div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>6pm - 10pm</h4><p>Somewhere</p></div>
    </div>
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park sponsored by White Knight Racing</div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>9am - 5pm</h4><p>Xtreme Raceway Park</p></div>
    </div>
    """

    events = parse_tmccc_page_events_impl(html)

    assert len(events) == 1
    assert events[0]["title"] == "Race #1 Xtreme Raceway Park sponsored by White Knight Racing"


def test_parse_tmccc_page_events_prefers_desktop_card_details():
    html = """
    <div data-aid="CALENDAR_SMALLER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park</div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>9am</h4><h4>-</h4><h4>5pm</h4></div>
    </div>
    <div data-aid="CALENDAR_BIGGER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">3/22/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #1 Xtreme Raceway Park</div>
      <div data-aid="CALENDAR_DESC_TEXT">
        <p>Track Phone: 972-544-3724</p>
        <p>Website: https://www.xtremeracewaypark.com/</p>
        <p>*1/4 Mile*</p>
      </div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>9am</h4><h4>-</h4><h4>5pm</h4></div>
      <p>1800 South I-45 Service Rd., Ferris, TX 75125</p>
    </div>
    """

    events = parse_tmccc_page_events_impl(html)

    assert events == [{
        "title": "Race #1 Xtreme Raceway Park",
        "date_text": "3/22/2026",
        "time_text": "9am - 5pm",
        "location_text": "1800 South I-45 Service Rd., Ferris, TX 75125",
        "description": "Track Phone: 972-544-3724\nWebsite: https://www.xtremeracewaypark.com/\n*1/4 Mile*",
        "track_phone": "972-544-3724",
        "track_website": "https://www.xtremeracewaypark.com/",
        "series": "TMCCC",
        "classes_text": (
            "Stock Muscle, Street Muscle, King Muscle, EV Muscle, Competition Muscle, "
            "Modified Muscle, Electronics, Pro Muscle, Super Pro Muscle, CA$H Bracket"
        ),
    }]


def test_parse_tmccc_page_events_uses_real_location_not_end_time():
    html = """
    <div data-aid="CALENDAR_BIGGER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">4/25/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #3 Little River Dragway</div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>3pm</h4><h4>-</h4><h4>11pm</h4></div>
      <p>13550 State Hwy 95, Holland, TX 76534</p>
      <div data-aid="CALENDAR_DESC_TEXT"><p>*4 points 1st round*</p></div>
    </div>
    """

    event = parse_tmccc_page_events_impl(html)[0]

    assert event["time_text"] == "3pm - 11pm"
    assert event["location_text"] == "13550 State Hwy 95, Holland, TX 76534"


def test_parse_tmccc_page_events_handles_time_block_without_h4_text():
    html = """
    <div data-aid="CALENDAR_BIGGER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">4/25/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #3 Little River Dragway</div>
      <div data-aid="CALENDAR_EVENT_TIME"></div>
      <p>13550 State Hwy 95, Holland, TX 76534</p>
      <div data-aid="CALENDAR_DESC_TEXT"></div>
    </div>
    """

    event = parse_tmccc_page_events_impl(html)[0]

    assert event["time_text"] is None
    assert event["location_text"] == "13550 State Hwy 95, Holland, TX 76534"


def test_parse_tmccc_page_events_returns_none_location_when_missing():
    html = """
    <div data-aid="CALENDAR_BIGGER_SCREEN_CONTAINER">
      <div data-aid="CALENDAR_EVENT_DATE">4/25/2026</div>
      <div data-aid="CALENDAR_EVENT_TITLE">Race #3 Little River Dragway</div>
      <div data-aid="CALENDAR_EVENT_TIME"><h4>3pm</h4><h4>-</h4><h4>11pm</h4></div>
      <div data-aid="CALENDAR_DESC_TEXT"><p>*4 points 1st round*</p></div>
    </div>
    """

    event = parse_tmccc_page_events_impl(html)[0]

    assert event["location_text"] is None


def test_parse_tmccc_description_extracts_phone_website_and_notes():
    result = parse_tmccc_description(
        "Track Phone: 405-413-1522\nWebsite: https://www.thundervalleyracewaypark.com\n*1/4 Mile*\n**4 Points 1st Round**"
    )

    assert result == {
        "phone": "405-413-1522",
        "website": "https://www.thundervalleyracewaypark.com",
        "notes": ["1/4 Mile", "4 Points 1st Round"],
    }


def test_parse_tmccc_description_skips_blank_lines():
    result = parse_tmccc_description("\n\nTrack Phone: 405-413-1522\n\n")

    assert result == {"phone": "405-413-1522", "website": None, "notes": []}


def test_parse_tmccc_city_state_reads_city_and_state_from_address():
    assert parse_tmccc_city_state("633 FM 369 , Iowa Park TX 76367") == ("Iowa Park", "TX")


def test_parse_tmccc_city_state_returns_none_for_non_address_text():
    assert parse_tmccc_city_state("not a location") == (None, None)


def test_enrich_tmccc_extracted_event_fills_missing_fields_from_listing():
    extracted = {
        "title": "Race #2 Thunder Valley Raceway Park",
        "event_type": "points_race",
        "track": {"name": "Thunder Valley Raceway Park", "city": None, "state": None},
        "dates": {"start": "2026-04-12"},
        "times": {"gates_open": "08:00"},
        "classes": None,
        "contact": None,
        "confidence": 0.65,
        "notes": None,
    }
    listing = {
        "source": "TMCCC",
        "location_text": "10500 48th St., Lexington, OK 73051",
        "description": "*1/4 Mile*\n**4 Points 1st Round**\nTrack Phone: 405-413-1522\nWebsite: https://www.thundervalleyracewaypark.com",
    }

    enriched = enrich_tmccc_extracted_event(extracted, listing)

    assert enriched["track"]["city"] == "Lexington"
    assert enriched["track"]["state"] == "OK"
    assert enriched["contact"] == {
        "phone": "405-413-1522",
        "website": "https://www.thundervalleyracewaypark.com",
    }
    assert enriched["series"] == "TMCCC"
    assert "Super Pro Muscle" in enriched["classes"]
    assert "1/4 Mile" in enriched["notes"]

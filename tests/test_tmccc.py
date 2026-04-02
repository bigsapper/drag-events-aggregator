from drag_events.strategies.tmccc import parse_tmccc_page_events_impl


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

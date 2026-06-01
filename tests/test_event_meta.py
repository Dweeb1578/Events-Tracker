from agents.event_meta import parse_event_city, parse_event_date


def test_city_nyc_variants():
    assert parse_event_city("Join us for a CFO dinner in NYC next week") == "NYC"
    assert parse_event_city("An intimate roundtable in New York City") == "NYC"


def test_city_sf_variants():
    assert parse_event_city("Wine & finance leaders in San Francisco") == "SF"
    assert parse_event_city("Bay Area happy hour for controllers") == "SF"


def test_city_none_when_absent():
    assert parse_event_city("A virtual webinar for finance teams") == ""


def test_date_iso_and_month():
    assert parse_event_date("RSVP for our event on 2026-07-15") == "2026-07-15"
    assert parse_event_date("Dinner on July 15, 2026 in NYC") == "2026-07-15"


def test_date_none_when_absent():
    assert parse_event_date("Join our CFO dinner soon") == ""

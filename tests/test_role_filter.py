from agents.role_filter import normalize_org, role_prefilter


def test_normalize_org_strips_suffixes():
    assert normalize_org("OneBill, Inc.") == "onebill"
    assert normalize_org("Zone & Co (Zone Billing)") == "zone & co"


def test_drops_tracked_org_employee():
    tracked = {"orb", "metronome", "operators guild"}
    engagers = [
        {"name": "A", "parsed_title": "VP Finance", "parsed_company": "Orb"},
        {"name": "B", "parsed_title": "CFO", "parsed_company": "AcmeSaaS"},
    ]
    kept, counts = role_prefilter(engagers, tracked)
    assert [e["name"] for e in kept] == ["B"]
    assert counts["own_company"] == 1


def test_drops_non_icp_role():
    engagers = [
        {"name": "C", "parsed_title": "Software Engineer", "parsed_company": "AcmeSaaS"},
        {"name": "D", "parsed_title": "Controller", "parsed_company": "AcmeSaaS"},
    ]
    kept, counts = role_prefilter(engagers, set())
    assert [e["name"] for e in kept] == ["D"]
    assert counts["non_icp_role"] == 1


def test_fails_open_on_blank_title_and_company():
    engagers = [{"name": "E", "parsed_title": "", "parsed_company": ""}]
    kept, counts = role_prefilter(engagers, {"orb"})
    assert [e["name"] for e in kept] == ["E"]

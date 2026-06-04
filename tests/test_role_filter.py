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
    assert counts == {"own_company": 0, "non_icp_role": 0}


def test_normalize_org_no_leading_dot_when_suffix_at_start():
    out = normalize_org("Corp. Dev Partners")
    assert not out.startswith(".")
    assert not out.startswith(" ")


def test_load_tracked_orgs_normalizes_flat_list():
    from agents.role_filter import load_tracked_orgs
    tracked = load_tracked_orgs([{"name": "Orb"}, {"name": "Maxio LLC"}, {"foo": "bar"}])
    assert tracked == {"orb", "maxio"}


def test_engager_company_matches_tracked_after_suffix_strip():
    engagers = [{"name": "X", "parsed_title": "CFO", "parsed_company": "Maxio LLC"}]
    kept, counts = role_prefilter(engagers, {"maxio"})
    assert kept == []
    assert counts["own_company"] == 1


def test_both_counters_increment_in_one_call():
    engagers = [
        {"name": "Own", "parsed_title": "CFO", "parsed_company": "Orb"},
        {"name": "Eng", "parsed_title": "Software Engineer", "parsed_company": "AcmeSaaS"},
        {"name": "Good", "parsed_title": "Controller", "parsed_company": "AcmeSaaS"},
    ]
    kept, counts = role_prefilter(engagers, {"orb"})
    assert [e["name"] for e in kept] == ["Good"]
    assert counts == {"own_company": 1, "non_icp_role": 1}


def test_none_title_fails_open():
    engagers = [{"name": "N", "parsed_title": None, "parsed_company": "AcmeSaaS"}]
    kept, counts = role_prefilter(engagers, set())
    assert [e["name"] for e in kept] == ["N"]

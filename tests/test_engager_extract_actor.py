from agents.engager_extractor import extract_engagers_from_actor


def _raw(name, headline, url, etype, post="p1"):
    return {"name": name, "headline": headline, "linkedin_url": url,
            "engagement_type": etype, "source_post_url": post}


def test_parses_headline_into_title_and_company():
    out = extract_engagers_from_actor([_raw("Jane Doe", "VP Finance at AcmeSaaS",
                                            "https://linkedin.com/in/ACoAA1", "liker")])
    assert out[0]["parsed_title"] == "VP Finance"
    assert out[0]["parsed_company"] == "AcmeSaaS"


def test_dedup_by_url_keeps_stronger_engagement():
    rows = [
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1/", "liker"),
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1",  "commenter"),
    ]
    out = extract_engagers_from_actor(rows)
    assert len(out) == 1
    assert out[0]["engagement_type"] == "commenter"  # upgraded


def test_dedup_by_name_company_when_urls_differ():
    rows = [
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1", "liker"),
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/jane-doe", "commenter"),
    ]
    out = extract_engagers_from_actor(rows)
    assert len(out) == 1
    assert out[0]["engagement_type"] == "commenter"

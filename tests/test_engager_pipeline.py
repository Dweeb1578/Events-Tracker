from agents import engager_pipeline as ep


def test_pipeline_filters_classifies_and_sorts(monkeypatch):
    posts = [{"source_post_url": "p1", "source_post_company": "Orb",
              "post_text": "CFO dinner in NYC on 2026-07-15", "category": "billing"}]

    monkeypatch.setattr(ep, "scrape_post_engagers", lambda urls, results_limit=100: [
        {"name": "Jane Doe", "headline": "VP Finance at AcmeSaaS",
         "linkedin_url": "https://linkedin.com/in/ACoAA1", "engagement_type": "commenter",
         "source_post_url": "p1"},
        {"name": "Eng Person", "headline": "Software Engineer at AcmeSaaS",
         "linkedin_url": "https://linkedin.com/in/ACoAA2", "engagement_type": "liker",
         "source_post_url": "p1"},
        {"name": "Orb Staff", "headline": "AE at Orb",
         "linkedin_url": "https://linkedin.com/in/ACoAA3", "engagement_type": "liker",
         "source_post_url": "p1"},
    ])

    def fake_classify(e):
        e["icp_score"] = 86
        e["verdict"] = "STRONG ICP FIT"
        e["company"] = e["parsed_company"]
        e["title"] = e["parsed_title"]
        return e
    monkeypatch.setattr(ep, "classify_engager", fake_classify)

    out = ep.run_engager_pipeline(posts, tracked_orgs={"orb"})

    # engineer dropped (non-ICP role), Orb staff dropped (own company) -> only Jane
    assert len(out) == 1
    j = out[0]
    assert j["name"] == "Jane Doe"
    assert j["event_city"] == "NYC"
    assert j["event_date"] == "2026-07-15"
    assert j["engagement_strength"] == "high (comment)"
    assert "Orb" in j["warm_reason"]
    assert j["source_post_company"] == "Orb"

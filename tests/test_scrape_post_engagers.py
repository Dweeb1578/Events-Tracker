from agents import linkedin_scraper


def test_scrape_post_engagers_normalizes_items(monkeypatch):
    fake_items = [
        {"type": "likers", "url_profile": "https://www.linkedin.com/in/ACoAA111",
         "name": "Jane Doe", "subtitle": "VP Finance at AcmeSaaS",
         "post_Link": "https://www.linkedin.com/posts/orb-activity-1"},
        {"type": "commenters", "url_profile": "https://www.linkedin.com/in/ACoAA222",
         "name": "John Roe", "subtitle": "Controller at Beta Inc",
         "post_Link": "https://www.linkedin.com/posts/orb-activity-1"},
    ]
    monkeypatch.setattr(linkedin_scraper, "_run_engagers_actor", lambda urls, limit: fake_items)

    out = linkedin_scraper.scrape_post_engagers(
        ["https://www.linkedin.com/posts/orb-activity-1"], results_limit=50)

    assert len(out) == 2
    assert out[0] == {
        "name": "Jane Doe",
        "headline": "VP Finance at AcmeSaaS",
        "linkedin_url": "https://www.linkedin.com/in/ACoAA111",
        "engagement_type": "liker",
        "source_post_url": "https://www.linkedin.com/posts/orb-activity-1",
    }
    assert out[1]["engagement_type"] == "commenter"


def test_scrape_post_engagers_skips_blank(monkeypatch):
    fake_items = [{"type": "likers", "url_profile": "", "name": "", "subtitle": "", "post_Link": ""}]
    monkeypatch.setattr(linkedin_scraper, "_run_engagers_actor", lambda urls, limit: fake_items)
    assert linkedin_scraper.scrape_post_engagers(["x"]) == []


def test_scrape_post_engagers_empty_input_returns_empty():
    assert linkedin_scraper.scrape_post_engagers([]) == []


def test_scrape_post_engagers_handles_credit_error(monkeypatch):
    import requests

    def boom(urls, limit):
        raise requests.exceptions.HTTPError("402 Payment Required")

    monkeypatch.setattr(linkedin_scraper, "_run_engagers_actor", boom)
    assert linkedin_scraper.scrape_post_engagers(["x"]) == []

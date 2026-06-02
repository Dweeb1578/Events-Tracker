from agents import orchestrator


def test_run_engager_stage_calls_pipeline(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(orchestrator, "scrape_posts_with_comments", lambda sources: [
        {"source_post_url": "p1", "source_post_company": "Orb",
         "post_text": "CFO dinner in NYC", "category": "billing"}])

    def fake_pipeline(posts, tracked_orgs, results_limit=100):
        captured["posts"] = posts
        captured["tracked"] = tracked_orgs
        return [{"name": "Jane", "icp_score": 86, "verdict": "STRONG ICP FIT"}]
    monkeypatch.setattr(orchestrator, "run_engager_pipeline", fake_pipeline)

    written = {}
    monkeypatch.setattr(orchestrator, "write_engagers",
                        lambda eng, output_path, dry_run=False: written.setdefault("n", len(eng)))

    sources = [{"company": "Orb", "category": "billing",
                "linkedin_url": "https://linkedin.com/company/orbhq"}]
    n = orchestrator.run_engager_stage(sources, output_path=str(tmp_path / "o.xlsx"),
                                       sheet_id=None, dry_run=False)

    assert n == 1
    assert "orb" in captured["tracked"]
    assert captured["posts"][0]["source_post_company"] == "Orb"
    assert written["n"] == 1

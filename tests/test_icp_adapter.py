from agents import icp_adapter


def test_classify_engager_merges_fields(monkeypatch):
    monkeypatch.setattr(icp_adapter, "_enrich_profile", lambda url: {
        "company_name": "AcmeSaaS", "industry": "software", "employee_count": 300,
        "location": "New York, US", "person_title": "VP Finance", "email": "j@acmesaas.com"})
    monkeypatch.setattr(icp_adapter, "_classify_company", lambda enriched: {
        "success": True, "weighted_score": 8.6, "verdict": "STRONG ICP FIT",
        "verdict_emoji": "✅", "company_name": "AcmeSaaS"})

    e = {"name": "Jane", "linkedin_url": "https://linkedin.com/in/ACoAA1",
         "parsed_title": "VP Finance", "parsed_company": "AcmeSaaS"}
    out = icp_adapter.classify_engager(e)

    assert out["icp_score"] == 86            # 8.6/10 -> 0-100 scale
    assert out["verdict"] == "STRONG ICP FIT"
    assert out["company"] == "AcmeSaaS"
    assert out["title"] == "VP Finance"
    assert out["email"] == "j@acmesaas.com"


def test_classify_engager_handles_failure(monkeypatch):
    monkeypatch.setattr(icp_adapter, "_enrich_profile", lambda url: {"error": "no match"})
    monkeypatch.setattr(icp_adapter, "_classify_company", lambda enriched: {"success": False, "error": "x"})
    e = {"name": "Jane", "linkedin_url": "u", "parsed_title": "VP Finance", "parsed_company": "AcmeSaaS"}
    out = icp_adapter.classify_engager(e)
    assert out["icp_score"] == 0
    assert out["verdict"] == "ERROR"

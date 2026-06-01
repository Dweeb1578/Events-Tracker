import pdl_enricher


PDL_OK = {
    "status": 200,
    "data": {
        "full_name": "Jane Doe",
        "job_title": "VP of Finance",
        "job_company_name": "AcmeSaaS",
        "job_company_size": "201-500",
        "job_company_industry": "computer software",
        "location_name": "New York, New York, United States",
        "location_country": "united states",
        "work_email": "jane@acmesaas.com",
    },
}


def test_map_pdl_person_to_schema():
    out = pdl_enricher.map_pdl_person(PDL_OK["data"])
    assert out["person_title"] == "VP of Finance"
    assert out["company_name"] == "AcmeSaaS"
    assert out["employee_count"] == 350          # midpoint of 201-500
    assert out["industry"] == "computer software"
    assert out["country"] == "united states"
    assert out["email"] == "jane@acmesaas.com"


def test_enrich_via_pdl_returns_none_on_miss(monkeypatch):
    monkeypatch.setenv("PDL_API_KEY", "x")
    monkeypatch.setattr(pdl_enricher, "_pdl_get", lambda params: {"status": 404, "data": None})
    assert pdl_enricher.enrich_via_pdl(linkedin_url="https://linkedin.com/in/ACoAA1") is None


def test_enrich_via_pdl_skips_without_key(monkeypatch):
    monkeypatch.delenv("PDL_API_KEY", raising=False)
    assert pdl_enricher.enrich_via_pdl(name="Jane", company="AcmeSaaS") is None

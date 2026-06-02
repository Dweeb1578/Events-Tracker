"""Adapter around the copied icp_classification engine. Isolates the sys.path import."""
import os
import sys

_ICP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icp_classification")
if _ICP not in sys.path:
    sys.path.insert(0, _ICP)

from enrichment import enrich_profile as _enrich_profile      # noqa: E402
from classifier import classify_company as _classify_company  # noqa: E402


def classify_engager(engager: dict) -> dict:
    """
    Enrich + classify one engager via the ICP engine; merge results onto the dict.
    Score is converted from the engine's 0-10 weighted_score to a 0-100 icp_score
    (matches the colour thresholds the writers already use: >=70 green, >=50 amber).
    """
    url = engager.get("linkedin_url", "")
    enriched = _enrich_profile(url) if url else {"error": "no url"}
    result = _classify_company(enriched)

    if not result.get("success"):
        engager["icp_score"] = 0
        engager["verdict"] = "ERROR"
        engager["enriched"] = False
        return engager

    engager["icp_score"] = int(round(result.get("weighted_score", 0) * 10))
    engager["verdict"] = result.get("verdict", "")
    engager["company"] = enriched.get("company_name", "") or engager.get("parsed_company", "")
    engager["title"] = enriched.get("person_title", "") or engager.get("parsed_title", "")
    engager["email"] = enriched.get("email", "")
    engager["company_size"] = enriched.get("employee_count", "")
    engager["industry"] = enriched.get("industry", "")
    engager["location"] = enriched.get("location", "")
    engager["enriched"] = True
    return engager

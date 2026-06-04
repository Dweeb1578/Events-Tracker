"""People Data Labs person enrichment (PDL-first). Returns normalized dict or None."""
import os
import re

import httpx

PDL_URL = "https://api.peopledatalabs.com/v5/person/enrich"


def _midpoint(size_range: str) -> int | None:
    """'201-500' -> 350 ; '10001+' -> 10001 ; '' -> None."""
    if not size_range:
        return None
    nums = [int(n) for n in re.findall(r"\d+", size_range.replace(",", ""))]
    if len(nums) == 2:
        return (nums[0] + nums[1]) // 2
    return nums[0] if nums else None


def map_pdl_person(data: dict) -> dict:
    """Map a PDL person record onto the enrichment schema used by classifier._build_company_context."""
    emails = data.get("personal_emails") or []
    email = data.get("work_email", "") or (emails[0] if emails else "")
    return {
        "source": "pdl",
        "person_name": data.get("full_name", ""),
        "person_title": data.get("job_title", ""),
        "person_headline": data.get("job_title", ""),
        "company_name": data.get("job_company_name", "") or "Unknown",
        "industry": data.get("job_company_industry", "") or "Unknown",
        "employee_count": _midpoint(data.get("job_company_size", "")),
        "location": data.get("location_name", "") or "Unknown",
        "country": data.get("location_country", "") or "Unknown",
        "email": email,
        "enriched": True,
    }


def _pdl_get(params: dict) -> dict:
    """Raw PDL call. Returns {'status': int, 'data': dict|None}."""
    key = os.getenv("PDL_API_KEY", "")
    try:
        r = httpx.get(PDL_URL, params={**params, "min_likelihood": 6},
                      headers={"X-Api-Key": key}, timeout=15)
        body = r.json()
        return {"status": r.status_code, "data": body.get("data")}
    except Exception as e:
        print(f"[pdl] request failed: {e}")
        return {"status": 0, "data": None}


def enrich_via_pdl(linkedin_url: str = "", name: str = "", company: str = "") -> dict | None:
    """Try PDL by profile (preferred) or name+company. Returns mapped dict or None."""
    if not os.getenv("PDL_API_KEY"):
        return None
    params = {}
    if linkedin_url:
        params["profile"] = linkedin_url
    if name:
        params["name"] = name
    if company:
        params["company"] = company
    if not params:
        return None
    res = _pdl_get(params)
    if res["status"] == 200 and res["data"]:
        return map_pdl_person(res["data"])
    return None

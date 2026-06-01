"""
Data enrichment layer — fetches company info from email domains and LinkedIn profiles.
Uses Apollo.io for email-based enrichment and Apify for LinkedIn scraping.
"""

import os
import re
import json
import httpx
from apify_client import ApifyClient
from dotenv import load_dotenv
from pdl_enricher import enrich_via_pdl

load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")

# Common free email domains — if someone uses these, we can't enrich from domain
FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "aol.com", "icloud.com", "mail.com", "protonmail.com", "proton.me",
    "zoho.com", "yandex.com", "gmx.com", "fastmail.com",
}


def extract_domain_from_email(email: str) -> str | None:
    """Extract company domain from an email address."""
    email = email.strip().lower()
    match = re.match(r"[^@]+@(.+)", email)
    if not match:
        return None
    domain = match.group(1)
    if domain in FREE_EMAIL_DOMAINS:
        return None
    return domain


def is_linkedin_url(text: str) -> bool:
    """Check if a string is a LinkedIn URL."""
    text = text.strip().lower()
    return "linkedin.com/in/" in text or "linkedin.com/company/" in text


def extract_linkedin_url(text: str) -> str:
    """Clean and normalize a LinkedIn URL."""
    text = text.strip()
    # Add https if missing
    if not text.startswith("http"):
        text = "https://" + text
    # Remove trailing slashes and query params
    text = text.split("?")[0].rstrip("/")
    return text


def enrich_from_email(email: str) -> dict | None:
    """
    Enrich company data from an email address using Apollo.io.
    Returns normalized company data dict or None if enrichment fails.
    """
    domain = extract_domain_from_email(email)
    if not domain:
        return {
            "source": "email",
            "email": email,
            "error": f"Cannot enrich — {'free email provider' if '@' in email else 'invalid email'}",
            "company_name": None,
            "domain": None,
        }

    # Try Apollo Organization Search API (more reliable than /enrich on free tier)
    try:
        response = httpx.post(
            "https://api.apollo.io/v1/organizations/search",
            json={"q_organization_domains": domain},
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_API_KEY,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        orgs = data.get("organizations", [])
        org = orgs[0] if orgs else {}

        if not org or not org.get("name"):
            result = _fallback_enrichment(email, domain)
        else:
            result = _normalize_apollo_org(org, email, domain)

        # Supplement with finance persona search
        company_name = result.get("company_name", "")
        finance_people = _search_finance_people(domain, company_name)
        if finance_people:
            result["finance_people"] = finance_people

        # Supplement with website scraping if description is missing
        if not result.get("description") and not result.get("short_description"):
            web_info = _scrape_website(domain)
            if web_info:
                result["description"] = web_info.get("description", "")
                if not result.get("short_description"):
                    result["short_description"] = web_info.get("description", "")[:200]

        # Scrape pricing page
        pricing_text = _scrape_pricing_page(domain)
        if pricing_text:
            result["pricing_page_content"] = pricing_text

        return result

    except Exception as e:
        print(f"[enrichment] Apollo API error for {domain}: {e}")
        result = _fallback_enrichment(email, domain)

        # Still try website scraping on Apollo failure
        web_info = _scrape_website(domain)
        if web_info:
            result["description"] = web_info.get("description", "")
            result["short_description"] = web_info.get("description", "")[:200]

        return result


def _search_finance_people(domain: str, company_name: str = "") -> list[dict]:
    """
    Find finance personas at the company using Google search via Apify.
    Searches for finance titles on LinkedIn and parses results.
    """
    if not company_name:
        company_name = domain.split(".")[0].title()

    # Build search query: look for finance/accounting people on LinkedIn
    finance_titles = (
        'CFO OR "Chief Accounting Officer" OR Controller OR '
        '"VP Finance" OR "VP Accounting" OR '
        '"Head of Finance" OR "Head of Accounting" OR '
        '"Director of Finance" OR "Director of Accounting" OR '
        '"Head of Billing" OR "Head of Revenue Accounting" OR '
        '"Revenue Operations" OR "Business Systems"'
    )
    query = f'"{company_name}" {finance_titles} site:linkedin.com'

    results = _google_search(query, max_results=5)

    if not results:
        # Fallback: broader search without site:linkedin.com
        query2 = f'"{company_name}" CFO OR Controller OR "VP Finance" OR "VP Accounting" OR "Chief Accounting Officer"'
        results = _google_search(query2, max_results=5)

    if not results:
        return []

    # Parse search results to extract people and titles
    return _extract_people_from_search_results(results, company_name)


def _google_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a Google search via Apify and return results."""
    try:
        client = ApifyClient(APIFY_API_TOKEN)
        actor_call = client.actor("nFJndFXA5zjCTuudP").call(
            run_input={
                "queries": query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": max_results,
                "languageCode": "en",
                "countryCode": "us",
            },
            timeout_secs=30,
        )

        items = list(client.dataset(actor_call["defaultDatasetId"]).iterate_items())
        results = []
        for item in items:
            organic = item.get("organicResults", [])
            for r in organic[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "description": r.get("description", ""),
                    "url": r.get("url", ""),
                })
        return results

    except Exception as e:
        print(f"[enrichment] Google search error: {e}")
        return []


def _extract_people_from_search_results(results: list[dict], company_name: str) -> list[dict]:
    """Extract finance people names and titles from Google search results."""
    finance_keywords = [
        # Finance
        "cfo", "chief financial officer", "controller", "comptroller",
        "financial controller", "global controller", "vp controller",
        "svp of finance", "avp of finance",
        "vp finance", "vp of finance", "vice president finance",
        "vice president, finance", "vp, finance",
        "director of finance", "director finance", "director of financial operations",
        "head of finance", "head of financial operations",
        "head of financial transformation",
        "fractional cfo",
        # Accounting
        "cao", "chief accounting officer",
        "svp of accounting", "avp of accounting",
        "vp accounting", "vp of accounting",
        "director of accounting", "director accounting",
        "head of accounting",
        # Revenue & Billing
        "head of billing", "head of order to cash",
        "head of revenue accounting", "director of revenue accounting",
        "revenue accounting manager", "billing manager", "revenue manager",
        "finance manager", "accounting manager",
        # Rev-Ops / Business Systems
        "vp of revenue operations", "director of rev-ops", "head of rev-ops",
        "head of business systems", "head of business applications",
        "head of enterprise systems", "head of business technology",
        "revops", "revenue operations", "bizops", "business operations",
        # Operations
        "coo", "chief operating officer",
        "director of business operations", "head of business operations",
        # Product / Tech / Eng
        "cto", "chief technology officer",
        "cpo", "chief product officer",
        "vp of product", "vp of engineering",
        "head of product", "head of engineering",
        "fp&a", "fpa",
        "head of gtm finance",
    ]

    found_people = []
    seen = set()

    for result in results:
        title = result.get("title", "")
        desc = result.get("description", "")
        combined = f"{title} {desc}".lower()

        # Check if this result mentions a finance role
        matched_title = None
        for kw in finance_keywords:
            if kw in combined:
                matched_title = kw
                break

        if not matched_title:
            continue

        # Try to extract name from the search result title
        name = _extract_name_from_search_title(title)

        # Also try to find a better finance title from the full text
        display_title = _find_best_finance_title(f"{title} {desc}", finance_keywords)

        if name and name.lower() not in seen:
            seen.add(name.lower())
            found_people.append({"name": name, "title": display_title})

    return found_people[:5]


def _find_best_finance_title(text: str, finance_keywords: list[str]) -> str:
    """Find the most specific finance title mentioned in text."""
    text_lower = text.lower()
    # Prefer more specific titles over generic ones
    priority_order = [
        # Finance
        ("chief financial officer", "CFO"),
        ("cfo", "CFO"),
        ("fractional cfo", "Fractional CFO"),
        ("vice president, finance & controller", "VP Finance & Controller"),
        ("svp of finance", "SVP of Finance"),
        ("avp of finance", "AVP of Finance"),
        ("vice president finance", "VP Finance"),
        ("vice president, finance", "VP Finance"),
        ("vp of finance", "VP Finance"),
        ("vp finance", "VP Finance"),
        ("vp, finance", "VP Finance"),
        ("financial controller", "Financial Controller"),
        ("global controller", "Global Controller"),
        ("vp controller", "VP Controller"),
        ("controller", "Controller"),
        ("comptroller", "Controller"),
        ("head of financial transformation", "Head of Financial Transformation"),
        ("head of financial operations", "Head of Financial Operations"),
        ("head of gtm finance", "Head of GTM Finance"),
        ("head of finance", "Head of Finance"),
        ("director of financial operations", "Director of Financial Operations"),
        ("director of finance", "Director of Finance"),
        ("director finance", "Director of Finance"),
        ("financial transformation manager", "Financial Transformation Manager"),
        ("finance manager", "Finance Manager"),
        # Accounting
        ("chief accounting officer", "Chief Accounting Officer"),
        ("cao", "Chief Accounting Officer"),
        ("svp of accounting", "SVP of Accounting"),
        ("avp of accounting", "AVP of Accounting"),
        ("vp of accounting", "VP Accounting"),
        ("vp accounting", "VP Accounting"),
        ("head of accounting", "Head of Accounting"),
        ("director of accounting", "Director of Accounting"),
        ("accounting manager", "Accounting Manager"),
        # Revenue & Billing
        ("head of revenue accounting", "Head of Revenue Accounting"),
        ("director of revenue accounting", "Director of Revenue Accounting"),
        ("revenue accounting manager", "Revenue Accounting Manager"),
        ("head of billing", "Head of Billing"),
        ("head of order to cash", "Head of Order to Cash"),
        ("billing manager", "Billing Manager"),
        ("revenue manager", "Revenue Manager"),
        # Rev-Ops / Business Systems
        ("vp of revenue operations", "VP of Revenue Operations"),
        ("director of rev-ops", "Director of Rev-Ops"),
        ("head of rev-ops", "Head of Rev-Ops"),
        ("head of business systems", "Head of Business Systems"),
        ("head of business applications", "Head of Business Applications"),
        ("head of enterprise systems", "Head of Enterprise Systems"),
        ("head of business technology", "Head of Business Technology"),
        ("revenue operations", "RevOps"),
        ("revops", "RevOps"),
        ("business operations", "BizOps"),
        ("bizops", "BizOps"),
        # Operations
        ("chief operating officer", "COO"),
        ("coo", "COO"),
        ("director of business operations", "Director of Business Operations"),
        ("head of business operations", "Head of Business Operations"),
        # Product / Tech / Eng
        ("chief technology officer", "CTO"),
        ("cto", "CTO"),
        ("chief product officer", "CPO"),
        ("cpo", "CPO"),
        ("vp of product", "VP of Product"),
        ("vp of engineering", "VP of Engineering"),
        ("head of product", "Head of Product"),
        ("head of engineering", "Head of Engineering"),
        ("fp&a", "FP&A"),
    ]
    for keyword, display in priority_order:
        if keyword in text_lower:
            return display
    return "Finance"


def _extract_name_from_search_title(title: str) -> str | None:
    """Extract a person's name from a Google/LinkedIn search result title."""
    # Common LinkedIn patterns:
    # "Harlan Fong CPA, MBA - Vice President, Finance & Controller at ..."
    # "John Smith - CFO - Stripe | LinkedIn"
    # "Alex Small - Head of Finance, Strategy, & Operations for ..."
    # "Stripe CFO joins the board of ..."  (not a person profile)

    # Remove common suffixes
    for suffix in ["| LinkedIn", "- LinkedIn"]:
        if suffix in title:
            title = title[:title.index(suffix)].strip()

    # Split by " - " or " – " (common LinkedIn separator)
    parts = re.split(r'\s*[-–]\s*', title, maxsplit=1)

    if not parts:
        return None

    name_candidate = parts[0].strip()

    # Remove credentials like "CPA", "MBA", "PhD", "CFA" etc.
    # These appear as "Harlan Fong CPA, MBA" or "John Smith, CPA"
    name_candidate = re.sub(r',?\s*\b(CPA|MBA|PhD|CFA|ACCA|CA|CMA|MSc|BSc|MD|JD|Esq)\b', '', name_candidate, flags=re.IGNORECASE)
    name_candidate = name_candidate.strip().rstrip(',').strip()

    # Validate: name should be 2-5 words, mostly alphabetic
    words = name_candidate.split()
    if len(words) < 2 or len(words) > 5:
        return None

    # Check that most words look like name parts (allow periods for initials like "J.")
    name_chars = sum(1 for w in words if re.match(r'^[A-Za-z][A-Za-z.\'-]*$', w))
    if name_chars < len(words) * 0.7:
        return None

    # Skip if the "name" is actually a company name or article title
    skip_words = {"stripe", "board", "joins", "the", "cfo", "company", "announces"}
    if words[0].lower() in skip_words:
        return None

    return name_candidate


def _scrape_website(domain: str) -> dict | None:
    """Scrape company website for description and signals (free, no API needed)."""
    try:
        response = httpx.get(
            f"https://{domain}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"},
            timeout=10,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None

        html = response.text[:5000]  # Only need the head/first part

        # Extract meta description
        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
                html, re.IGNORECASE
            )

        description = desc_match.group(1) if desc_match else ""

        # Extract title
        title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        return {"description": description, "title": title}

    except Exception as e:
        print(f"[enrichment] Website scrape error for {domain}: {e}")
        return None


def _scrape_pricing_page(domain: str) -> str | None:
    """Fetch pricing page content from common URL patterns. Returns plain text or None."""
    paths = ["/pricing", "/plans", "/pricing-plans", "/pricing-page", "/price"]
    for path in paths:
        try:
            response = httpx.get(
                f"https://{domain}{path}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; bot)"},
                timeout=8,
                follow_redirects=True,
            )
            if response.status_code != 200:
                continue
            # Strip HTML tags, collapse whitespace, truncate
            text = re.sub(r"<[^>]+>", " ", response.text)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) < 100:
                continue
            return text[:3000]
        except Exception:
            continue
    return None


def _normalize_apollo_org(org: dict, email: str, domain: str) -> dict:
    """Normalize Apollo organization data into our standard format."""
    return {
        "source": "apollo",
        "email": email,
        "domain": domain,
        "company_name": org.get("name", "Unknown"),
        "industry": org.get("industry") or org.get("industry_tag_name") or "Unknown",
        "keywords": org.get("keywords", []),
        "short_description": org.get("short_description", ""),
        "description": (org.get("seo_description") or org.get("short_description") or "")[:500],
        "employee_count": _parse_employee_count(org),
        "estimated_revenue": org.get("estimated_num_employees"),
        "annual_revenue_printed": org.get("annual_revenue_printed", ""),
        "location": _build_location(org),
        "country": org.get("country", "Unknown"),
        "city": org.get("city", ""),
        "state": org.get("state", ""),
        "founded_year": org.get("founded_year"),
        "linkedin_url": org.get("linkedin_url", ""),
        "website_url": org.get("website_url") or f"https://{domain}",
        "technologies": org.get("current_technologies", [])[:10],
        "funding_total": org.get("total_funding_printed", ""),
        "latest_funding_round": org.get("latest_funding_round_type", ""),
        "raw_data": org,  # Keep raw for LLM context
    }


def _parse_employee_count(org: dict) -> int | None:
    """Parse employee count from Apollo data."""
    # Try direct count first
    count = org.get("estimated_num_employees")
    if count and isinstance(count, (int, float)):
        return int(count)

    # Try range string like "51-200"
    range_str = org.get("employee_count") or org.get("employees_range")
    if range_str and isinstance(range_str, str):
        # Parse "51-200" → average
        parts = range_str.replace(",", "").split("-")
        try:
            if len(parts) == 2:
                return (int(parts[0]) + int(parts[1])) // 2
            return int(parts[0])
        except ValueError:
            pass

    return None


def _build_location(org: dict) -> str:
    """Build a human-readable location string."""
    parts = []
    if org.get("city"):
        parts.append(org["city"])
    if org.get("state"):
        parts.append(org["state"])
    if org.get("country"):
        parts.append(org["country"])
    return ", ".join(parts) if parts else "Unknown"


def _fallback_enrichment(email: str, domain: str) -> dict:
    """Minimal enrichment when Apollo fails — returns domain info only."""
    return {
        "source": "fallback",
        "email": email,
        "domain": domain,
        "company_name": domain.split(".")[0].title(),
        "industry": "Unknown",
        "keywords": [],
        "short_description": "",
        "description": "",
        "employee_count": None,
        "location": "Unknown",
        "country": "Unknown",
        "city": "",
        "state": "",
        "founded_year": None,
        "linkedin_url": "",
        "website_url": f"https://{domain}",
        "technologies": [],
        "funding_total": "",
        "latest_funding_round": "",
    }


def enrich_from_linkedin(linkedin_url: str) -> dict | None:
    """
    Enrich profile/company data from a LinkedIn URL using Apify.
    Supports both personal profiles (/in/) and company pages (/company/).
    """
    url = extract_linkedin_url(linkedin_url)

    # PDL-first: try a single PDL person call (disambiguates by profile URL).
    pdl = enrich_via_pdl(linkedin_url=url)
    if pdl:
        domain = pdl.get("domain")
        if domain:
            pricing = _scrape_pricing_page(domain)
            if pricing:
                pdl["pricing_page_content"] = pricing
        return pdl
    # else fall through to the existing Apify + Apollo path (Apollo fallback)

    try:
        client = ApifyClient(APIFY_API_TOKEN)

        if "/company/" in url:
            profile_data = _scrape_linkedin_company(client, url)
        else:
            profile_data = _scrape_linkedin_person(client, url)

        # Supplement with Apollo data using company name or URL
        company_name = profile_data.get("company_name")
        company_url = profile_data.get("company_linkedin_url")
        if company_name and company_name != "Unknown":
            # Try title-cased name if original is all-lowercase (e.g. "dataplor" → "Dataplor")
            if company_name == company_name.lower():
                company_name = company_name.title()
            apollo_data = _apollo_enrich_company_search(company_name, linkedin_url=company_url)
            if apollo_data:
                _merge_enrichment_data(profile_data, apollo_data)

        # Scrape pricing page if we have a domain
        domain = profile_data.get("domain")
        if domain:
            pricing_text = _scrape_pricing_page(domain)
            if pricing_text:
                profile_data["pricing_page_content"] = pricing_text

        return profile_data

    except Exception as e:
        print(f"[enrichment] Apify error for {url}: {e}")
        return {
            "source": "linkedin",
            "linkedin_url": url,
            "error": f"LinkedIn enrichment failed: {str(e)}",
            "company_name": None,
        }


def _scrape_linkedin_person(client: ApifyClient, url: str) -> dict:
    """Scrape a LinkedIn personal profile via Apify."""
    actor_call = client.actor("harvestapi/linkedin-profile-scraper").call(
        run_input={
            "urls": [url],
        },
        timeout_secs=120,
    )

    items = list(client.dataset(actor_call["defaultDatasetId"]).iterate_items())
    if not items:
        return {
            "source": "linkedin_person",
            "linkedin_url": url,
            "error": "No profile data returned",
            "company_name": None,
        }

    profile = items[0]

    current_position = (profile.get("currentPosition") or [{}])[0]
    current_company = current_position.get("companyName")
    company_linkedin_url = current_position.get("companyLinkedinUrl")

    location_obj = profile.get("location", {})
    location = location_obj.get("linkedinText", "") if isinstance(location_obj, dict) else str(location_obj)
    country = location_obj.get("parsed", {}).get("country", "Unknown") if isinstance(location_obj, dict) else "Unknown"

    return {
        "source": "linkedin_person",
        "linkedin_url": url,
        "person_name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
        "person_title": profile.get("headline", ""),
        "person_headline": profile.get("headline", ""),
        "company_name": current_company or "Unknown",
        "company_linkedin_url": company_linkedin_url,
        "industry": "Unknown",  # Not in personal profile; enriched via Apollo downstream
        "location": location,
        "country": country,
        "description": profile.get("about", ""),
        "employee_count": None,  # Not available from personal profile
        "raw_data": profile,
    }


def _scrape_linkedin_company(client: ApifyClient, url: str) -> dict:
    """Scrape a LinkedIn company page via Apify."""
    actor_call = client.actor("thescrappa/linkedin-company-scraper").call(
        run_input={
            "urls": [url],
        },
        timeout_secs=60,
    )

    items = list(client.dataset(actor_call["defaultDatasetId"]).iterate_items())
    if not items:
        return {
            "source": "linkedin_company",
            "linkedin_url": url,
            "error": "No company data returned",
            "company_name": None,
        }

    company = items[0]

    return {
        "source": "linkedin_company",
        "linkedin_url": url,
        "company_name": company.get("name", "Unknown"),
        "industry": company.get("industry", "Unknown"),
        "description": (company.get("about", "") or company.get("description", "") or "")[:500],
        "employee_count": company.get("company_size", "") or company.get("staffCount"),
        "location": company.get("headquarters", "Unknown") if isinstance(company.get("headquarters"), str) else "Unknown",
        "country": "Unknown",
        "website_url": company.get("website", ""),
        "specialities": company.get("specialties", []),
        "founded_year": company.get("founded", None),
    }


def enrich_profile(input_text: str) -> dict:
    """
    Main enrichment entry point.
    Detects whether input is an email or LinkedIn URL and enriches accordingly.
    """
    input_text = input_text.strip()

    if is_linkedin_url(input_text):
        return enrich_from_linkedin(input_text)
    elif "@" in input_text:
        return enrich_from_email(input_text)
    else:
        return {
            "source": "unknown",
            "error": f"Cannot determine input type: '{input_text}'. Please provide an email address or LinkedIn URL.",
            "company_name": None,
        }

def _apollo_enrich_company_search(company_name: str, linkedin_url: str = None) -> dict | None:
    """Search for a company in Apollo by linkedin URL or name and return normalized data."""
    try:
        # Prefer LinkedIn URL to avoid ambiguous names (like "Rain")
        payload = {}
        if linkedin_url:
            payload["q_organization_linkedin_url"] = linkedin_url
        else:
            payload["q_organization_name"] = company_name
            
        response = httpx.post(
            "https://api.apollo.io/v1/organizations/search",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": APOLLO_API_KEY,
            },
            timeout=15,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        orgs = data.get("organizations", [])
        
        # If we failed using the LinkedIn URL, fall back to searching precisely by name
        if not orgs and linkedin_url:
            payload = {"q_organization_name": company_name}
            response = httpx.post(
                "https://api.apollo.io/v1/organizations/search",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key": APOLLO_API_KEY,
                },
                timeout=15,
            )
            data = response.json()
            orgs = data.get("organizations", [])
            
        if not orgs:
            return None

        # Sanity check: top match name should loosely match what we searched for.
        # If it doesn't (e.g. LinkedIn numeric URL returned Google), fall back to name search.
        top_name = (orgs[0].get("name") or "").lower()
        search_name = company_name.lower()
        name_words = [w for w in search_name.split() if len(w) > 2]
        if name_words and not any(w in top_name for w in name_words):
            if linkedin_url:
                # LinkedIn URL returned wrong results — retry with name only
                payload = {"q_organization_name": company_name}
                response = httpx.post(
                    "https://api.apollo.io/v1/organizations/search",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": APOLLO_API_KEY,
                    },
                    timeout=15,
                )
                data = response.json()
                orgs = data.get("organizations", [])
                if not orgs:
                    return None
                top_name = (orgs[0].get("name") or "").lower()
                if name_words and not any(w in top_name for w in name_words):
                    return None
            else:
                return None

        # Take the top match
        org = orgs[0]
        domain = org.get("primary_domain", "")
        
        result = _normalize_apollo_org(org, email="", domain=domain)
        
        # We can also fetch finance people like we do for email enrichment
        if domain:
            finance_people = _search_finance_people(domain, org.get("name", company_name))
            if finance_people:
                result["finance_people"] = finance_people
                
        return result
        
    except Exception as e:
        print(f"[enrichment] Apollo search error for {company_name}: {e}")
        return None


def _merge_enrichment_data(profile_data: dict, apollo_data: dict) -> None:
    """Merge Apollo company data into the LinkedIn profile data in-place."""
    # We trust Apollo more for company-level stats
    fields_to_merge = [
        "domain", "industry", "keywords", "short_description", "description",
        "employee_count", "estimated_revenue", "annual_revenue_printed",
        "location", "country", "city", "state", "founded_year", "website_url",
        "technologies", "funding_total", "latest_funding_round", "finance_people"
    ]
    
    for field in fields_to_merge:
        if apollo_data.get(field) and (not profile_data.get(field) or profile_data.get(field) == "Unknown"):
            profile_data[field] = apollo_data[field]
        elif apollo_data.get(field) and field in ["employee_count", "annual_revenue_printed", "funding_total", "technologies", "keywords", "finance_people", "industry"]:
            # Override specific fields where Apollo is definitively better than a personal LinkedIn profile
            profile_data[field] = apollo_data[field]

"""
Agent 1: URL Discovery Agent
Manages the list of companies and generates event source URLs to scrape.
"""

import os
import yaml
from urllib.parse import quote_plus


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "companies.yaml")


def load_companies(config_path: str = CONFIG_PATH) -> list[dict]:
    """Load companies from YAML config, returns flat list of company dicts."""
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    companies = []
    for category, company_list in data.items():
        for company in company_list:
            companies.append({
                "name": company["name"],
                "category": category,
                "event_urls": company.get("event_urls") or [],
                "linkedin_url": company.get("linkedin_url", ""),
            })
    return companies


def generate_search_urls(company_name: str) -> list[dict]:
    """Generate dynamic search URLs for a company on event platforms."""
    encoded = quote_plus(company_name)
    urls = []

    # Luma search — searches for events the company is hosting/sponsoring
    urls.append({
        "url": f"https://lu.ma/search?q={encoded}",
        "source_type": "luma_search",
    })

    # Google search for events (fallback, disabled by default via --include-google)
    urls.append({
        "url": f"https://www.google.com/search?q={encoded}+finance+event+summit+2025+2026",
        "source_type": "google_search",
    })

    return urls


def discover_urls(config_path: str = CONFIG_PATH) -> list[dict]:
    """
    Main discovery function.
    Returns a flat list of { company, category, url, source_type } dicts.
    """
    companies = load_companies(config_path)
    all_urls = []

    for company in companies:
        # Static URLs from config
        for url in company["event_urls"]:
            all_urls.append({
                "company": company["name"],
                "category": company["category"],
                "url": url,
                "source_type": "company_website",
            })

        # Dynamic search URLs
        for search_url in generate_search_urls(company["name"]):
            all_urls.append({
                "company": company["name"],
                "category": company["category"],
                "url": search_url["url"],
                "source_type": search_url["source_type"],
            })

    print(f"[Discovery] Found {len(all_urls)} URLs across {len(companies)} companies")
    return all_urls


if __name__ == "__main__":
    urls = discover_urls()
    for u in urls[:10]:
        print(f"  {u['company']} ({u['source_type']}): {u['url']}")
    print(f"  ... and {len(urls) - 10} more")

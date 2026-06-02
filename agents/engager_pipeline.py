"""Orchestrates the engager flow: scrape → dedup → meta → role filter → ICP → extras → sort."""
import logging

from agents.linkedin_scraper import scrape_post_engagers
from agents.engager_extractor import extract_engagers_from_actor
from agents.event_meta import parse_event_city, parse_event_date
from agents.role_filter import role_prefilter
from agents.icp_adapter import classify_engager
from agents.engager_scoring import engagement_strength, warm_reason

logger = logging.getLogger(__name__)


def run_engager_pipeline(posts: list[dict], tracked_orgs: set[str],
                         results_limit: int = 100) -> list[dict]:
    """
    posts: dicts with source_post_url, source_post_company, post_text, category.
    Returns engager dicts sorted by icp_score desc.
    """
    if not posts:
        return []

    # index post metadata by URL
    meta = {}
    for p in posts:
        url = p.get("source_post_url", "")
        meta[url] = {
            "source_post_company": p.get("source_post_company", ""),
            "source_post_category": p.get("category", ""),
            "source_post_preview": (p.get("post_text", "") or "")[:100].strip(),
            "event_city": parse_event_city(p.get("post_text", "")),
            "event_date": parse_event_date(p.get("post_text", "")),
        }

    post_urls = [p["source_post_url"] for p in posts if p.get("source_post_url")]
    raw = scrape_post_engagers(post_urls, results_limit=results_limit)
    engagers = extract_engagers_from_actor(raw)
    print(f"  [Engagers] {len(engagers)} unique after dedup")

    # attach post-level metadata
    for e in engagers:
        e.update(meta.get(e.get("source_post_url", ""), {}))

    kept, counts = role_prefilter(engagers, tracked_orgs)
    print(f"  [Engagers] role filter dropped {counts['own_company']} own-company, "
          f"{counts['non_icp_role']} non-ICP roles → {len(kept)} to classify")

    classified = []
    for e in kept:
        e = classify_engager(e)
        e["engagement_strength"] = engagement_strength(e.get("engagement_type", ""))
        e["warm_reason"] = warm_reason(e)
        classified.append(e)

    classified.sort(key=lambda x: x.get("icp_score", 0), reverse=True)
    return classified

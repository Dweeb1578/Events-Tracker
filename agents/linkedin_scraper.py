"""
Agent 1b: LinkedIn Company Post Scraper via Apify
Uses Apify's "Company Posts Scraper for LinkedIn (No Cookies)" actor to pull
recent posts from competitor company LinkedIn pages.

Approach: Open each company's LinkedIn page → grab last 5 posts → done.
Only 35 API calls for 35 companies (or 1 call if using batch actor).
No LinkedIn login/cookies needed.

Setup:
1. Sign up at https://apify.com (free, no credit card)
2. Get your API token from Settings → Integrations
3. Add APIFY_API_TOKEN to your .env file
"""

import os
import logging
import time

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

APIFY_API_BASE = "https://api.apify.com/v2"

# "LinkedIn Company Posts Scraper (No Cookies)" by harvestapi
# Extracts public posts from a LinkedIn company page, no cookies needed
# https://apify.com/harvestapi/linkedin-company-posts
# $2 per 1,000 results (cheaper than apimaestro's $5/1K)
ACTOR_ID = "harvestapi~linkedin-company-posts"

# How many recent posts to grab per company
POSTS_PER_COMPANY = 5


def _get_token() -> str:
    """Get Apify API token."""
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise ValueError(
            "APIFY_API_TOKEN not set. Sign up (free) at https://apify.com "
            "and get your token from Settings → Integrations"
        )
    return token


def _run_actor_for_company(linkedin_url: str, max_posts: int = POSTS_PER_COMPANY) -> list[dict]:
    """
    Run the Apify actor for a single company LinkedIn page.
    Returns list of post dicts from the actor output.
    """
    token = _get_token()

    # Extract the company page URL (strip /posts/ suffix if present)
    company_url = linkedin_url.rstrip("/")
    if company_url.endswith("/posts"):
        company_url = company_url[:-6]

    actor_input = {
        "targetUrls": [company_url],
        "maxPosts": max_posts,
        "scrapeReactions": False,
        "scrapeComments": False,
    }

    # Start the actor run (note: actor ID uses ~ not / in API URL)
    url = f"{APIFY_API_BASE}/acts/{ACTOR_ID}/runs?token={token}"
    resp = requests.post(url, json=actor_input, timeout=30)
    resp.raise_for_status()
    run_data = resp.json()["data"]
    run_id = run_data["id"]

    # Poll for completion (max 2 minutes)
    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}?token={token}"
    for _ in range(24):
        time.sleep(5)
        status_resp = requests.get(status_url, timeout=15)
        status_resp.raise_for_status()
        status = status_resp.json()["data"]["status"]

        if status == "SUCCEEDED":
            break
        elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
            logger.warning(f"[Apify] Run {status} for {username}")
            return []
    else:
        logger.warning(f"[Apify] Timed out for {username}")
        return []

    # Get results from the dataset
    dataset_id = status_resp.json()["data"]["defaultDatasetId"]
    items_url = f"{APIFY_API_BASE}/datasets/{dataset_id}/items?token={token}"
    items_resp = requests.get(items_url, timeout=30)
    items_resp.raise_for_status()

    return items_resp.json()


def _extract_posts_from_result(raw_results: list | dict) -> list[dict]:
    """
    Extract post list from Apify harvestapi result.
    The actor returns a flat list of post dicts.
    """
    if isinstance(raw_results, list):
        return raw_results
    if isinstance(raw_results, dict):
        if "data" in raw_results:
            data = raw_results["data"]
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "posts" in data:
                return data["posts"]
        if "posts" in raw_results:
            return raw_results["posts"]
    return []


def scrape_linkedin_posts(companies: list[dict], max_posts_per_company: int = POSTS_PER_COMPANY) -> list[dict]:
    """
    Scrape LinkedIn company posts for event announcements.

    Opens each company's LinkedIn page and grabs their last N posts.
    Much cheaper than keyword searches — only 1 API call per company.

    Args:
        companies: List of dicts with 'company', 'category', 'linkedin_url'
        max_posts_per_company: How many recent posts to grab (default: 5)

    Returns:
        List of scraped items in the standard format for the classifier.
    """
    if not companies:
        return []

    # Filter to companies with LinkedIn URLs
    with_linkedin = [c for c in companies if c.get("linkedin_url")]
    if not with_linkedin:
        print("[LinkedIn] No companies have LinkedIn URLs configured")
        return []

    print(f"\n🔗 Scraping LinkedIn posts from {len(with_linkedin)} company pages via Apify...")
    print(f"   ({max_posts_per_company} posts per company, {len(with_linkedin)} companies = "
          f"{len(with_linkedin)} API calls)")

    results = []
    errors = 0

    for i, company_info in enumerate(with_linkedin):
        company = company_info["company"]
        category = company_info.get("category", "unknown")
        linkedin_url = company_info["linkedin_url"]

        print(f"  ({i+1}/{len(with_linkedin)}) {company}...", end=" ", flush=True)

        try:
            raw_results = _run_actor_for_company(linkedin_url, max_posts=max_posts_per_company)
        except ValueError as e:
            # No API token — abort all
            print(f"\n  ⚠️ {e}")
            return results
        except requests.exceptions.HTTPError as e:
            if "402" in str(e) or "Payment" in str(e):
                print(f"💰 Credits exhausted, stopping LinkedIn scraping")
                break
            print(f"✗ HTTP error: {e}")
            errors += 1
            continue
        except Exception as e:
            print(f"✗ Error: {e}")
            errors += 1
            continue

        # Extract posts from the result
        posts = _extract_posts_from_result(raw_results)

        post_count = 0
        for post in posts:
            # harvestapi actor uses 'content' for post text
            text = post.get("content", "") or post.get("text", "") or post.get("postText", "") or ""
            if not text or len(text.strip()) < 20:
                continue

            post_url = post.get("linkedinUrl", "") or post.get("url", "") or post.get("postUrl", "") or ""

            # Get post date
            posted_at = ""
            content_attrs = post.get("contentAttributes", {})
            if isinstance(content_attrs, dict):
                posted_at = content_attrs.get("postedAt", "")
            if not posted_at:
                posted_at = post.get("postedAt", "") or post.get("publishedAt", "")

            results.append({
                "company": company,
                "category": category,
                "source_url": post_url,
                "source_type": "linkedin_post",
                "raw_text": text,
                "scrape_method": "apify",
                "scraped_at": posted_at,
            })
            post_count += 1

        print(f"✓ {post_count} posts")

        # Small delay between companies to be respectful
        if i < len(with_linkedin) - 1:
            time.sleep(2)

    print(f"\n  [LinkedIn] Total: {len(results)} posts from {len(with_linkedin) - errors} companies")
    if errors:
        print(f"  [LinkedIn] Errors: {errors} companies failed")

    return results


if __name__ == "__main__":
    # Test with one company
    test = [
        {
            "company": "Ramp",
            "category": "accounts_payable",
            "linkedin_url": "https://www.linkedin.com/company/raboramp/posts/",
        },
    ]
    results = scrape_linkedin_posts(test, max_posts_per_company=3)
    for r in results:
        print(f"\n{'='*60}")
        print(f"{r['company']} | {r['source_url']}")
        print(r["raw_text"][:300])

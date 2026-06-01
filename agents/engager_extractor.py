"""
Engager Extractor
Parses LinkedIn post comment data from Apify results to extract
people who engaged with event-related posts. Deduplicates by
LinkedIn profile URL.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _parse_headline(headline: str) -> tuple[str, str]:
    """
    Parse a LinkedIn headline into (title, company).
    Handles patterns like:
      "CFO at Acme Corp"
      "VP Finance | Acme Corp | Board Member"
      "Chief Financial Officer - Acme (YC S20)"
      "Head of Billing @ Acme Corp"
    Returns ("", "") if unparsable.
    """
    if not headline:
        return ("", "")

    headline = headline.strip()

    # Try " at " split first (most common LinkedIn pattern)
    for separator in (" at ", " @ "):
        if separator in headline.lower():
            idx = headline.lower().index(separator)
            title = headline[:idx].strip()
            rest = headline[idx + len(separator):].strip()
            # Company is the first segment before | or -
            company = re.split(r"\s*[|–—]\s*", rest)[0].strip()
            # Strip parentheticals from company name
            company = re.sub(r"\s*\(.*?\)", "", company).strip()
            if title and company:
                return (title, company)

    # Try " | " split (e.g., "CFO | Acme Corp | Board Member")
    if " | " in headline:
        parts = [p.strip() for p in headline.split("|")]
        if len(parts) >= 2:
            return (parts[0], parts[1])

    # Try " - " split (e.g., "CFO - Acme Corp")
    if " - " in headline:
        parts = [p.strip() for p in headline.split(" - ", 1)]
        if len(parts) == 2:
            return (parts[0], parts[1])

    # Can't parse — return the whole headline as title, empty company
    return (headline, "")


def _extract_commenter(comment: dict, post_info: dict) -> dict | None:
    """Extract engager data from a single Apify comment object.

    The harvestapi actor uses a nested 'actor' object:
        {
            "commentary": "comment text",
            "actor": {
                "name": "Jane Smith",
                "linkedinUrl": "https://linkedin.com/in/...",
                "position": "CFO at Acme Corp"
            }
        }
    """
    # harvestapi nests commenter info under "actor"
    actor = comment.get("actor", {}) or {}

    name = (
        actor.get("name", "")
        or comment.get("author", "")
        or comment.get("authorName", "")
        or comment.get("name", "")
        or ""
    )
    if not name or not isinstance(name, str):
        return None

    linkedin_url = (
        actor.get("linkedinUrl", "")
        or actor.get("linkedin_url", "")
        or comment.get("authorUrl", "")
        or comment.get("authorProfileUrl", "")
        or ""
    )

    headline = (
        actor.get("position", "")
        or comment.get("authorHeadline", "")
        or comment.get("headline", "")
        or ""
    )

    comment_text = (
        comment.get("commentary", "")
        or comment.get("text", "")
        or comment.get("comment", "")
        or ""
    )

    parsed_title, parsed_company = _parse_headline(headline)

    return {
        "name": name.strip(),
        "linkedin_url": linkedin_url.strip(),
        "headline": headline.strip(),
        "parsed_title": parsed_title,
        "parsed_company": parsed_company,
        "engagement_type": "comment",
        "comment_text": comment_text.strip()[:500],
        "source_post_url": post_info.get("source_post_url", ""),
        "source_post_company": post_info.get("source_post_company", ""),
        "source_post_preview": post_info.get("source_post_preview", ""),
    }


_STRENGTH = {"liker": 1, "commenter": 2}


def _stronger(a: str, b: str) -> str:
    return a if _STRENGTH.get(a, 0) >= _STRENGTH.get(b, 0) else b


def extract_engagers_from_actor(rows: list[dict]) -> list[dict]:
    """
    Normalize + dedup engagers from scrape_post_engagers() output.
    Dedup key: normalized LinkedIn URL, with name|company as a fallback key so a
    person who both liked and commented (different URL forms) merges once.
    Keeps the stronger engagement_type (commenter > liker).
    When two records merge via the name|company fallback, the first-seen record's linkedin_url is kept.
    """
    by_key: dict[str, dict] = {}
    order: list[str] = []

    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        headline = (row.get("headline") or "").strip()
        title, company = _parse_headline(headline)
        url = (row.get("linkedin_url") or "").strip()
        etype = (row.get("engagement_type", "liker") or "liker").lower()

        url_key = url.rstrip("/").lower() if url else ""
        nc_key = f"{name.lower()}|{company.lower()}" if company else ""

        existing_key = url_key if url_key in by_key else (nc_key if nc_key in by_key else None)
        if existing_key:
            cur = by_key[existing_key]
            cur["engagement_type"] = _stronger(cur["engagement_type"], etype)
            continue

        engager = {
            "name": name,
            "linkedin_url": url,
            "headline": headline,
            "parsed_title": title,
            "parsed_company": company,
            "engagement_type": etype,
            "source_post_url": row.get("source_post_url", ""),
        }
        key = url_key or nc_key or f"__noidx_{len(order)}"
        by_key[key] = engager
        if nc_key and nc_key != key:
            by_key[nc_key] = engager  # alias so later URL-less dupes merge
        order.append(key)

    return [by_key[k] for k in order]


def extract_engagers(posts_with_comments: list[dict]) -> list[dict]:
    """
    Extract and deduplicate engagers from LinkedIn posts with comment data.

    Args:
        posts_with_comments: List of dicts, each containing:
            - "comments": list of comment objects from Apify
            - "source_post_url": URL of the LinkedIn post
            - "source_post_company": company that made the post
            - "source_post_preview": first 100 chars of post text

    Returns:
        Deduplicated list of engager dicts.
    """
    seen_urls = set()
    seen_names = set()  # fallback dedup when URL is missing
    engagers = []
    total_comments = 0

    for post in posts_with_comments:
        comments = post.get("comments", [])
        if not comments or not isinstance(comments, list):
            continue

        post_info = {
            "source_post_url": post.get("source_post_url", ""),
            "source_post_company": post.get("source_post_company", ""),
            "source_post_preview": post.get("source_post_preview", ""),
        }

        for comment in comments:
            if not isinstance(comment, dict):
                continue
            total_comments += 1

            engager = _extract_commenter(comment, post_info)
            if not engager:
                continue

            # Deduplicate by LinkedIn URL (preferred) or name (fallback)
            url = engager["linkedin_url"]
            name_lower = engager["name"].lower()

            if url:
                # Normalize URL for dedup
                normalized = url.rstrip("/").lower()
                if normalized in seen_urls:
                    continue
                seen_urls.add(normalized)
            else:
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

            engagers.append(engager)

    logger.info(
        f"Extracted {len(engagers)} unique engagers from "
        f"{total_comments} comments across {len(posts_with_comments)} posts"
    )
    return engagers

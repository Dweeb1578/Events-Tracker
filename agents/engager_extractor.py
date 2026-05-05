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

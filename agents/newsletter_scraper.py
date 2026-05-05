"""
Agent 1c: Newsletter / RSS Scraper

Pulls recent items from finance-newsletter RSS/Atom feeds and emits any whose
title or summary mentions an in-person event. Output shape matches the web
scraper so downstream classification works unchanged.

Adding a feed: append a dict to NEWSLETTER_FEEDS.
"""

import logging
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser

from agents.scraper import EVENT_KEYWORDS

logger = logging.getLogger(__name__)

# Curated feeds. Verify a URL by visiting it in a browser — most publications
# expose the feed at /feed or /rss.
NEWSLETTER_FEEDS = [
    {"name": "CFO Dive",         "url": "https://www.cfodive.com/feeds/news/"},
    {"name": "The Daily Upside", "url": "https://www.thedailyupside.com/feed/"},
    {"name": "The SaaS CFO",     "url": "https://www.thesaascfo.com/feed/"},
    {"name": "Run the Numbers (Podcast)", "url": "https://anchor.fm/s/10e7a9a40/podcast/rss"},
]

# Only consider items posted within this window
DEFAULT_MAX_AGE_DAYS = 21


def _entry_published(entry) -> datetime | None:
    """Pull a UTC datetime from a feedparser entry, falling back across fields."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            try:
                return datetime.fromtimestamp(mktime(struct), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def _matches_event_keywords(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(kw in lowered for kw in EVENT_KEYWORDS)


def scrape_newsletters(
    feeds: list[dict] | None = None,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> list[dict]:
    """
    Parse each feed and return items mentioning in-person event keywords.

    Returns a list of scraped-data dicts:
        {company, category, source_url, source_type, raw_text, scrape_method, scraped_at}
    """
    feeds = feeds or NEWSLETTER_FEEDS
    if not feeds:
        return []

    print(f"\n📰 Scraping {len(feeds)} newsletter feeds (last {max_age_days} days)...")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    results = []
    errors = 0

    for feed_info in feeds:
        name = feed_info["name"]
        url = feed_info["url"]
        print(f"  · {name}...", end=" ", flush=True)

        try:
            parsed = feedparser.parse(url)
        except Exception as e:
            print(f"✗ {e}")
            errors += 1
            continue

        if parsed.bozo and not parsed.entries:
            err = getattr(parsed, "bozo_exception", "unknown")
            print(f"✗ feed error: {err}")
            errors += 1
            continue

        kept = 0
        skipped_old = 0
        for entry in parsed.entries:
            published = _entry_published(entry)
            if published and published < cutoff:
                skipped_old += 1
                continue

            title = entry.get("title", "") or ""
            summary = entry.get("summary", "") or entry.get("description", "") or ""
            combined = f"{title}\n{summary}"

            if not _matches_event_keywords(combined):
                continue

            link = entry.get("link", "") or url
            posted_at = published.strftime("%Y-%m-%d") if published else ""
            raw_text = combined
            if posted_at:
                raw_text = f"[Newsletter item from {name}, {posted_at}]\n{raw_text}"

            results.append({
                "company": name,
                "category": "newsletter",
                "source_url": link,
                "source_type": "newsletter",
                "raw_text": raw_text,
                "scrape_method": "feedparser",
                "scraped_at": posted_at,
            })
            kept += 1

        status = f"✓ {kept} event items"
        if skipped_old:
            status += f" ({skipped_old} skipped, older than {max_age_days}d)"
        print(status)

    print(f"\n  [Newsletters] Total: {len(results)} items from {len(feeds) - errors}/{len(feeds)} feeds")
    return results


if __name__ == "__main__":
    items = scrape_newsletters()
    for item in items[:5]:
        print(f"\n{'='*60}\n{item['company']} | {item['source_url']}\n{item['raw_text'][:300]}")

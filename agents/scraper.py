"""
Agent 2: Web Scraper Agent
Scrapes event pages and extracts raw text content for classification.
"""

import random
import time
import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Rotate user agents to avoid blocks
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Keywords that suggest event content (in-person focused)
EVENT_KEYWORDS = [
    "register", "rsvp", "summit", "dinner", "workshop",
    "conference", "event", "meetup", "roundtable", "networking",
    "in-person", "join us", "sign up", "save your spot",
    "keynote", "panel", "fireside chat", "happy hour",
    "cocktail", "reception", "gala", "breakfast", "luncheon",
    "masterclass", "forum", "invite-only", "exclusive",
    "reserve your spot", "limited seats", "get tickets", "attend",
]


def _get_headers() -> dict:
    """Get randomized request headers."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    """Aggressively remove boilerplate elements to reduce noise."""
    # Standard noise tags
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript",
                     "aside", "form", "iframe", "svg", "meta", "link"]):
        tag.decompose()

    # Remove cookie consent banners, login prompts, newsletter signups
    noise_classes = [
        "cookie", "consent", "gdpr", "privacy", "banner",
        "newsletter", "subscribe", "signup", "login", "signin",
        "popup", "modal", "overlay", "chatbot", "chat-widget",
        "social-share", "share-buttons", "breadcrumb",
    ]
    for cls in noise_classes:
        for el in soup.select(f"[class*='{cls}']"):
            el.decompose()
        for el in soup.select(f"[id*='{cls}']"):
            el.decompose()


def _extract_event_blocks(soup: BeautifulSoup, url: str) -> list[str]:
    """
    Extract text blocks from HTML that are likely event-related.
    Returns a list of text chunks containing potential event info.
    """
    _strip_boilerplate(soup)

    # Strategy 1: Look for structured event containers
    event_selectors = [
        "[class*='event']", "[class*='Event']",
        "[class*='summit']", "[class*='Summit']",
        "[data-event]", "[itemtype*='Event']",
        "article", ".card", "[class*='card']",
    ]

    blocks = []
    seen_texts = set()

    for selector in event_selectors:
        elements = soup.select(selector)
        for el in elements:
            text = el.get_text(separator=" ", strip=True)
            if (
                len(text) > 50
                and len(text) < 5000
                and text not in seen_texts
                and any(kw in text.lower() for kw in EVENT_KEYWORDS)
            ):
                blocks.append(text)
                seen_texts.add(text)

    # Strategy 2: If no structured blocks found, get the full page text
    if not blocks:
        full_text = soup.get_text(separator=" ", strip=True)
        if any(kw in full_text.lower() for kw in EVENT_KEYWORDS) and len(full_text) > 100:
            blocks.append(full_text[:8000])

    return blocks


def scrape_with_requests(url: str) -> dict | None:
    """Scrape a URL using requests + BeautifulSoup (for static HTML)."""
    try:
        response = requests.get(url, headers=_get_headers(), timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        blocks = _extract_event_blocks(soup, url)

        if blocks:
            return {
                "raw_text": "\n---\n".join(blocks),
                "method": "requests",
                "status": "success",
            }
        else:
            return {
                "raw_text": "",
                "method": "requests",
                "status": "no_events_found",
            }

    except requests.exceptions.RequestException as e:
        logger.warning(f"[Scraper] requests failed for {url}: {e}")
        return None


def scrape_with_playwright(url: str) -> dict | None:
    """Scrape a URL using Playwright (for JS-rendered pages like Luma)."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=random.choice(USER_AGENTS))
            page.goto(url, wait_until="networkidle", timeout=20000)

            # Wait a bit for dynamic content
            page.wait_for_timeout(2000)

            content = page.content()
            browser.close()

        soup = BeautifulSoup(content, "html.parser")
        blocks = _extract_event_blocks(soup, url)

        if blocks:
            return {
                "raw_text": "\n---\n".join(blocks),
                "method": "playwright",
                "status": "success",
            }
        else:
            return {
                "raw_text": "",
                "method": "playwright",
                "status": "no_events_found",
            }

    except Exception as e:
        logger.warning(f"[Scraper] Playwright failed for {url}: {e}")
        return None


# Sources that need JS rendering
JS_RENDERED_SOURCES = {"luma_search"}


def scrape_urls(url_list: list[dict]) -> list[dict]:
    """
    Main scraping function.
    Takes URL list from discovery agent, returns scraped results.
    """
    results = []
    total = len(url_list)

    for i, item in enumerate(url_list):
        url = item["url"]
        company = item["company"]
        source_type = item["source_type"]

        print(f"[Scraper] ({i+1}/{total}) Scraping {company} - {source_type}...")

        # Choose scraping method
        if source_type in JS_RENDERED_SOURCES:
            result = scrape_with_playwright(url)
        else:
            result = scrape_with_requests(url)
            # Fallback to playwright if requests fails
            if result is None:
                result = scrape_with_playwright(url)

        if result and result["raw_text"]:
            results.append({
                "company": company,
                "category": item["category"],
                "source_url": url,
                "source_type": source_type,
                "raw_text": result["raw_text"],
                "scrape_method": result["method"],
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            logger.info(f"[Scraper] No event content from {company} - {url}")

        # Random delay between requests (2-5 seconds)
        if i < total - 1:
            delay = random.uniform(2.0, 5.0)
            time.sleep(delay)

    print(f"[Scraper] Scraped {len(results)} pages with event content out of {total} URLs")
    return results


if __name__ == "__main__":
    # Quick test with a known event page
    test_urls = [
        {"company": "Stripe", "category": "billing", "url": "https://stripe.com/events", "source_type": "company_website"},
    ]
    results = scrape_urls(test_urls)
    for r in results:
        print(f"\n{r['company']}: {len(r['raw_text'])} chars")
        print(r["raw_text"][:500])

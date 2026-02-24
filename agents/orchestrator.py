"""Agent 5: Orchestrator
Chains all agents together and manages the pipeline execution.
Supports: web scraping, LinkedIn post scraping (Apify), JSON caching.
Each run creates a fresh timestamped Excel file with separate sheets
for web events and LinkedIn events.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from agents.discovery import discover_urls, load_companies
from agents.scraper import scrape_urls
from agents.classifier import classify_events
from agents.excel_writer import write_events, write_scraped_data, write_linkedin_events

logger = logging.getLogger(__name__)

SCRAPED_CACHE = os.path.join(os.path.dirname(__file__), "..", "output", "scraped_cache.json")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")


def _make_timestamped_path() -> str:
    """Generate a timestamped output filename like events_2026-02-24_18-34.xlsx."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f"events_{ts}.xlsx")


def run_pipeline(
    config_path: str | None = None,
    output_path: str | None = None,
    dry_run: bool = False,
    skip_google: bool = True,
    min_relevance: int = 5,
    use_cache: bool = False,
    skip_linkedin: bool = False,
) -> dict:
    """
    Run the full event detection pipeline.

    Args:
        config_path: Path to companies YAML config (uses default if None)
        output_path: Path to output Excel file (uses default if None)
        dry_run: If True, print events but don't write to Excel
        skip_google: If True, skip Google search URLs (they often block scrapers)
        min_relevance: Minimum relevance score to include (1-10)
        use_cache: If True, skip scraping and use cached scraped data
        skip_linkedin: If True, skip LinkedIn scraping via Apify

    Returns:
        Summary dict with stats
    """
    start_time = time.time()

    # Generate timestamped output file (ignore any user-provided path)
    if not output_path:
        output_path = _make_timestamped_path()

    print("=" * 60)
    print("🔍 Zenskar Event Detection Pipeline")
    print(f"   Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   Output:     {output_path}")
    print(f"   Dry run:    {dry_run}")
    print(f"   Cache:      {use_cache}")
    print(f"   LinkedIn:   {'skip' if skip_linkedin else 'enabled'}")
    print("=" * 60)

    # ── Check for cached scraped data ──
    linkedin_scraped = []  # initialized here, populated below if not skip_linkedin
    if use_cache and os.path.exists(SCRAPED_CACHE):
        print("\n📦 Loading cached scraped data...")
        with open(SCRAPED_CACHE, "r", encoding="utf-8") as f:
            scraped = json.load(f)
        print(f"   Loaded {len(scraped)} cached pages")
        url_count = len(scraped)
    else:
        # ── Agent 1: URL Discovery ──
        print("\n📋 STEP 1: Discovering URLs...")
        kwargs = {}
        if config_path:
            kwargs["config_path"] = config_path
        urls = discover_urls(**kwargs)

        if skip_google:
            urls = [u for u in urls if u["source_type"] != "google_search"]
            print(f"  (Skipped Google search URLs, {len(urls)} remaining)")

        url_count = len(urls)

        if not urls:
            print("⚠️  No URLs to scrape. Check your config/companies.yaml")
            return {"urls": 0, "scraped": 0, "events": 0, "new_events": 0}

        # ── Agent 2: Web Scraping ──
        print(f"\n🌐 STEP 2: Scraping {len(urls)} URLs...")
        scraped = scrape_urls(urls)

        # ── Agent 2b: LinkedIn Post Scraping (Apify) ──
        linkedin_scraped = []
        if not skip_linkedin:
            try:
                from agents.linkedin_scraper import scrape_linkedin_posts

                companies = load_companies(config_path) if config_path else load_companies()
                linkedin_companies = [
                    {"company": c["name"], "category": c["category"], "linkedin_url": c["linkedin_url"]}
                    for c in companies if c.get("linkedin_url")
                ]

                if linkedin_companies:
                    linkedin_scraped = scrape_linkedin_posts(linkedin_companies)
                    if linkedin_scraped:
                        print(f"   📎 Got {len(linkedin_scraped)} LinkedIn posts (separate sheet)")
            except Exception as e:
                print(f"   ⚠️ LinkedIn scraping skipped: {e}")

        if not scraped and not linkedin_scraped:
            print("⚠️  No event content found from any source")
            return {"urls": url_count, "scraped": 0, "events": 0, "new_events": 0}

        # Save scraped data as JSON cache for reuse
        os.makedirs(os.path.dirname(SCRAPED_CACHE), exist_ok=True)
        with open(SCRAPED_CACHE, "w", encoding="utf-8") as f:
            json.dump(scraped, f, indent=2, ensure_ascii=False)
        print(f"   💾 Cached scraped data to {SCRAPED_CACHE}")

    # ── Save scraped data to Excel ──
    if scraped:
        print(f"\n💾 Saving {len(scraped)} scraped pages to Excel (Scraped Data sheet)...")
        write_scraped_data(scraped, output_path=output_path)

    # ── Agent 3: LLM Classification (web) ──
    events = []
    if scraped:
        print(f"\n🤖 STEP 3a: Classifying {len(scraped)} web pages with Groq (Llama 3.3 70B)...")
        print("   (pre-filter → boilerplate strip → batch → classify)")
        events = classify_events(scraped, min_relevance=min_relevance)

    # ── Agent 3b: LLM Classification (LinkedIn) ──
    linkedin_events = []
    if linkedin_scraped:
        print(f"\n🤖 STEP 3b: Classifying {len(linkedin_scraped)} LinkedIn posts with Groq...")
        linkedin_events = classify_events(linkedin_scraped, min_relevance=min_relevance)

    total_events = len(events) + len(linkedin_events)
    if total_events == 0:
        print("⚠️  No relevant upcoming IN-PERSON events found (scraped data still saved)")
        return {"urls": url_count, "scraped": len(scraped), "events": 0, "new_events": 0}

    # ── Agent 4: Dedup + Excel Write ──
    new_count = 0
    if events:
        print(f"\n📝 STEP 4a: Writing {len(events)} web events to Excel...")
        new_count += write_events(events, output_path=output_path, dry_run=dry_run)

    if linkedin_events:
        print(f"\n📝 STEP 4b: Writing {len(linkedin_events)} LinkedIn events to Excel...")
        new_count += write_linkedin_events(linkedin_events, output_path=output_path, dry_run=dry_run)

    # ── Summary ──
    elapsed = time.time() - start_time
    linkedin_count = len(linkedin_scraped) if not use_cache else 0
    summary = {
        "urls": url_count,
        "scraped": len(scraped),
        "linkedin_posts": linkedin_count,
        "events": len(events),
        "new_events": new_count,
        "elapsed_seconds": round(elapsed, 1),
    }

    print("\n" + "=" * 60)
    print("✅ Pipeline Complete!")
    print(f"   📁 Output file:     {output_path}")
    print(f"   URLs scanned:       {summary['urls']}")
    print(f"   Pages scraped:      {summary['scraped']}")
    print(f"   LinkedIn posts:     {summary['linkedin_posts']}")
    print(f"   Events found:       {summary['events']} (in-person only)")
    print(f"   New events added:   {summary['new_events']}")
    print(f"   Time elapsed:       {summary['elapsed_seconds']}s")
    print("=" * 60)

    return summary

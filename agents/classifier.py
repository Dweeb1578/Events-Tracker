"""
Agent 3: LLM Classifier Agent
Uses Groq (free tier, Llama 3.3 70B) to classify events and extract structured data.

Optimizations:
- Keyword pre-filter: skips pages without event keywords before calling LLM
- Boilerplate stripping: cleans text before sending to LLM
- Batch mode: sends 3 pages per LLM call to reduce API calls + token overhead
- Virtual/webinar filter: rejects non-in-person events
"""

import json
import os
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client: Optional[Groq] = None
MODEL = "llama-3.3-70b-versatile"

# ── Keyword pre-filter ──
# Pages must contain at least one of these to be sent to the LLM
EVENT_KEYWORDS = [
    # Registration signals
    "register", "rsvp", "sign up", "reserve your spot", "save your spot",
    "limited seats", "reserve a seat", "get tickets", "attend",
    # Event types (in-person focused)
    "summit", "dinner", "conference", "roundtable", "meetup", "networking",
    "happy hour", "cocktail", "reception", "gala", "breakfast", "luncheon",
    "fireside chat", "masterclass", "forum", "panel", "keynote",
    "invite-only", "exclusive", "in-person",
    # Generic
    "event", "workshop",
]

# Virtual/webinar signals — pages with ONLY these (no in-person keywords) get skipped
VIRTUAL_ONLY_KEYWORDS = [
    "webinar", "virtual event", "zoom", "online event", "livestream",
    "live stream", "on-demand", "watch now", "tune in",
]

IN_PERSON_KEYWORDS = [
    "summit", "dinner", "roundtable", "meetup", "networking",
    "happy hour", "cocktail", "reception", "gala", "breakfast", "luncheon",
    "fireside chat", "invite-only", "exclusive", "in-person",
    "venue", "hotel", "convention center",
]

BATCH_SIZE = 3  # Number of pages per LLM call


def _get_client() -> Groq:
    """Get or create Groq client."""
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get your free key at: https://console.groq.com"
            )
        _client = Groq(api_key=api_key)
    return _client


def _get_system_prompt() -> str:
    """Build system prompt with current date for past-event filtering."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""You are an event detection agent for Zenskar, a B2B billing and revenue recognition platform.
TODAY'S DATE: {today}

Your job is to analyze scraped web page content and:
1. Determine if it contains information about real IN-PERSON events (summits, dinners, conferences, meetups, roundtables, networking events, happy hours, receptions).
2. Extract structured details for each event found.
3. Score each event's relevance to Zenskar's ICP (Ideal Customer Profile).

CRITICAL RULES:
- Only include UPCOMING or ONGOING events (date >= {today})
- SKIP any event whose date has already passed
- IGNORE webinars, virtual events, online events, live streams, and Zoom/Teams calls — we only want IN-PERSON events with a physical location
- Only extract ACTUAL events with dates, not blog posts, case studies, or product pages
- If a date is unclear, use the best approximation and note it
- Do NOT fabricate events that aren't in the content

ZENSKAR'S ICP - Events are HIGHLY relevant (score 7-10) if they target:
- CFOs, Controllers, VP/Director/Head of Finance or Accounting
- FP&A leaders, RevOps, BizOps, Deal Desk professionals
- Finance teams at B2B SaaS companies (150-2000 employees)
- Topics: billing, revenue recognition, subscription management, financial operations, SaaS metrics, ARR, pricing strategy

Events are MODERATELY relevant (score 4-6) if they target:
- General finance professionals
- Startup/tech founders discussing financial operations
- Accounting or tax professionals

Events are LOW relevance (score 1-3) if they target:
- Pure developer/engineering audiences
- Marketing/sales with no finance angle
- Consumer/B2C audiences
- HR, recruiting, or unrelated topics

You MUST respond with valid JSON in this exact format:
{{
  "is_event": true/false,
  "events": [
    {{
      "event_name": "string",
      "host_company": "string",
      "event_type": "Summit|Dinner|Conference|Roundtable|Meetup|Networking|Happy Hour|Workshop|Other",
      "date": "YYYY-MM-DD or as found",
      "location": "City, Venue (MUST be a physical location, not Virtual)",
      "target_audience": "who it targets",
      "registration_url": "URL or empty string",
      "description": "1-2 sentence summary",
      "relevance_score": 1-10
    }}
  ]
}}"""


def _is_past_event(date_str: str) -> bool:
    """Check if an event date is in the past."""
    today = datetime.now(timezone.utc).date()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            event_date = datetime.strptime(date_str.strip(), fmt).date()
            return event_date < today
        except ValueError:
            continue
    return False


def _has_event_keywords(text: str) -> bool:
    """Check if text contains any event keywords (pre-filter)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in EVENT_KEYWORDS)


def _is_virtual_only(text: str) -> bool:
    """Check if the page only mentions virtual events with no in-person signals."""
    text_lower = text.lower()
    has_virtual = any(kw in text_lower for kw in VIRTUAL_ONLY_KEYWORDS)
    has_in_person = any(kw in text_lower for kw in IN_PERSON_KEYWORDS)
    # If it has virtual keywords but NO in-person keywords, skip it
    return has_virtual and not has_in_person


def _clean_text(raw_text: str) -> str:
    """Strip boilerplate and compress text to save tokens."""
    # Remove common boilerplate phrases
    boilerplate = [
        r"cookie\s*(policy|consent|preferences|settings).*?[\.\n]",
        r"accept\s*(all)?\s*cookies.*?[\.\n]",
        r"privacy\s*policy.*?[\.\n]",
        r"terms\s*(of|and)\s*(service|use|conditions).*?[\.\n]",
        r"©\s*\d{4}.*?[\.\n]",
        r"all\s*rights\s*reserved.*?[\.\n]",
        r"subscribe\s*to\s*(our)?\s*newsletter.*?[\.\n]",
        r"follow\s*us\s*on\s*(social|twitter|linkedin|facebook).*?[\.\n]",
        r"(log\s*in|sign\s*in|create\s*account).*?[\.\n]",
    ]
    text = raw_text
    for pattern in boilerplate:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Collapse repeated separators
    text = re.sub(r"(---\s*){2,}", "---\n", text)

    # Truncate to save tokens (reduced from 6000 to 3000)
    if len(text) > 3000:
        text = text[:3000] + "\n[...truncated]"

    return text


def _build_batch_prompt(batch: list[dict]) -> str:
    """Build a single prompt for multiple scraped pages."""
    parts = []
    for idx, item in enumerate(batch, 1):
        cleaned = _clean_text(item["raw_text"])
        parts.append(f"""=== PAGE {idx} ===
Company: {item['company']}
Category: {item['category']}
Source URL: {item['source_url']}

{cleaned}
=== END PAGE {idx} ===""")

    combined = "\n\n".join(parts)
    return f"""Analyze the following {len(batch)} scraped pages and extract any UPCOMING IN-PERSON events.
IGNORE webinars, virtual events, and online-only events.
For each event found, score its relevance to finance leaders (CFOs, Controllers, VP Finance, FP&A).
Respond ONLY with valid JSON.

{combined}"""


def classify_events(scraped_items: list[dict], min_relevance: int = 5) -> list[dict]:
    """
    Classify scraped content using Groq (Llama 3.3 70B).
    Uses keyword pre-filter, boilerplate stripping, and batching to reduce token usage.
    """
    client = _get_client()
    all_events = []
    system_prompt = _get_system_prompt()

    # ── Step 1: Pre-filter ──
    filtered = []
    skipped_no_keywords = 0
    skipped_virtual = 0
    skipped_empty = 0

    for item in scraped_items:
        raw = item.get("raw_text", "")
        if not raw or len(raw.strip()) < 50:
            skipped_empty += 1
            continue
        if not _has_event_keywords(raw):
            skipped_no_keywords += 1
            continue
        if _is_virtual_only(raw):
            skipped_virtual += 1
            continue
        filtered.append(item)

    total_orig = len(scraped_items)
    total = len(filtered)
    print(f"[Classifier] Pre-filter: {total_orig} pages → {total} candidates")
    print(f"   Skipped: {skipped_empty} empty, {skipped_no_keywords} no keywords, {skipped_virtual} virtual-only")

    if not filtered:
        print("[Classifier] No pages passed pre-filter")
        return []

    # ── Step 2: Batch & classify ──
    batches = [filtered[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]
    print(f"[Classifier] Processing {total} pages in {len(batches)} batches (batch size {BATCH_SIZE})")

    for batch_idx, batch in enumerate(batches):
        companies = ", ".join(item["company"] for item in batch)
        print(f"\n[Classifier] Batch {batch_idx+1}/{len(batches)}: {companies}")

        user_prompt = _build_batch_prompt(batch)

        try:
            max_retries = 3
            response = None
            for attempt in range(max_retries):
                try:
                    response = client.chat.completions.create(
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=2000,
                        response_format={"type": "json_object"},
                    )
                    break
                except Exception as retry_err:
                    err_str = str(retry_err)
                    if ("rate_limit" in err_str.lower() or "429" in err_str) and attempt < max_retries - 1:
                        wait = 15 * (attempt + 1)
                        print(f"  ⏳ Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        raise

            if response is None:
                continue

            # Log token usage
            usage = response.usage
            if usage:
                print(f"  📊 Tokens: {usage.prompt_tokens} in / {usage.completion_tokens} out")

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            events_list = result.get("events", [])
            # Handle both single-page and batch response formats
            if not events_list and result.get("is_event"):
                events_list = []

            for event in events_list:
                # Filter past events
                if _is_past_event(event.get("date", "")):
                    print(f"  ⏭ Past: {event.get('event_name', '?')} ({event.get('date', '')})")
                    continue

                # Filter virtual events that slipped through
                loc = (event.get("location", "") or "").lower()
                etype = (event.get("event_type", "") or "").lower()
                if any(v in loc for v in ["virtual", "online", "zoom", "teams"]) or etype == "webinar":
                    print(f"  🚫 Virtual: {event.get('event_name', '?')}")
                    continue

                if event.get("relevance_score", 0) >= min_relevance:
                    # Map back to source company from batch
                    if not event.get("source_company"):
                        host = event.get("host_company", "").lower()
                        for item in batch:
                            if item["company"].lower() in host or host in item["company"].lower():
                                event["source_company"] = item["company"]
                                event["source_category"] = item["category"]
                                event["source_url"] = item["source_url"]
                                break
                        else:
                            event["source_company"] = batch[0]["company"]
                            event["source_category"] = batch[0]["category"]
                            event["source_url"] = batch[0]["source_url"]

                    all_events.append(event)
                    print(f"  ✓ {event['event_name']} | {event.get('location','?')} | relevance:{event['relevance_score']}")
                else:
                    print(f"  ✗ Low relevance ({event.get('relevance_score', 0)}): {event.get('event_name', '?')}")

        except json.JSONDecodeError as e:
            logger.error(f"[Classifier] JSON parse error batch {batch_idx+1}: {e}")
            print(f"  ✗ JSON parse error: {e}")
        except Exception as e:
            logger.error(f"[Classifier] Error batch {batch_idx+1}: {e}")
            print(f"  ✗ Error: {e}")

        # Rate-limit delay between batches
        if batch_idx < len(batches) - 1:
            time.sleep(4)

    print(f"\n[Classifier] Found {len(all_events)} relevant upcoming IN-PERSON events")
    return all_events


if __name__ == "__main__":
    test_data = [
        {
            "company": "Ramp",
            "category": "accounts_payable",
            "source_url": "https://ramp.com/events",
            "raw_text": """
            Join us for the CFO Summit 2026!
            Date: March 15, 2026
            Location: San Francisco, CA - The Ritz-Carlton
            An exclusive dinner and networking event for CFOs and Controllers
            at B2B SaaS companies. Topics include revenue recognition,
            billing automation, and financial operations.
            Register now at https://ramp.com/cfo-summit-2026
            """,
        },
        {
            "company": "Stripe",
            "category": "billing",
            "source_url": "https://stripe.com/events",
            "raw_text": """
            Stripe Sessions: The future of internet payments.
            A webinar on online payment processing. Join us on Zoom!
            Date: April 1, 2026. Virtual event. Register at stripe.com/webinar
            """,
        },
        {
            "company": "Zuora",
            "category": "billing",
            "source_url": "https://zuora.com/events",
            "raw_text": """
            Subscribed Live 2026 Conference
            Date: May 20-22, 2026
            Location: Las Vegas, NV - Wynn Hotel
            The premier subscription economy event. CFOs, Controllers, and
            finance leaders discuss ARR, billing automation, and revenue recognition.
            Early bird registration open. RSVP at subscribed.zuora.com
            """,
        },
    ]
    events = classify_events(test_data)
    for e in events:
        print(json.dumps(e, indent=2))

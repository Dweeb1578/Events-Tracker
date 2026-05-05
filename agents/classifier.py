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
MODEL = "openai/gpt-oss-120b"

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
    "google meet", "microsoft teams", "webex", "gotomeeting",
    "gotowebinar", "hopin", "airmeet", "bluejeans",
    "join online", "remote event", "digital event", "virtual summit",
    "online workshop", "virtual conference",
]

IN_PERSON_KEYWORDS = [
    "summit", "dinner", "roundtable", "meetup", "networking",
    "happy hour", "cocktail", "reception", "gala", "breakfast", "luncheon",
    "fireside chat", "invite-only", "exclusive", "in-person",
    "venue", "hotel", "convention center",
]

# Signals that an extracted event is virtual/online — checked against location,
# event_type, event_name, AND description after classification to catch anything
# the LLM missed.
VIRTUAL_SIGNALS = [
    "virtual", "online", "zoom", "teams", "webinar", "remote",
    "livestream", "live stream", "on-demand", "digital",
    "web conference", "google meet", "gotomeeting", "gotowebinar",
    "hopin", "airmeet", "webex", "bluejeans",
    "join online", "watch live", "register for free", "tune in",
    "stream live", "broadcast", "hybrid event", "hybrid format",
]

VIRTUAL_EVENT_TYPES = {
    "webinar", "virtual", "online", "livestream", "live stream",
    "virtual event", "online event", "digital event", "hybrid",
}

# Strong phrases that indicate a description is talking about an online event.
# These are lower-bar than VIRTUAL_SIGNALS — used only against description text
# where false positives are less harmful (description is freeform).
VIRTUAL_DESCRIPTION_PHRASES = [
    "join us online", "join us on zoom", "join us virtually",
    "online conference", "online summit", "online roundtable",
    "from anywhere", "wherever you are", "no travel required",
    "register to attend virtually", "streaming platform",
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
    return f"""You are an event extraction agent. You analyze scraped web pages and LinkedIn posts to find real, upcoming, IN-PERSON events relevant to B2B finance leaders.

TODAY'S DATE: {today}

━━━ TASK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For each page provided, determine whether it contains information about one or more real in-person events. For each event found, extract structured details and score its relevance.

━━━ WHAT COUNTS AS AN EVENT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INCLUDE only events that meet ALL of these criteria:
  1. STRICTLY in-person — held at a named physical venue (hotel, restaurant, conference center, office, named city + venue). MUST have a concrete physical address or named venue. A bare city name with NO venue is INSUFFICIENT unless the surrounding text clearly describes an in-person gathering.
  2. Upcoming — the event date is on or after {today}
  3. Real — the event actually exists in the source text (not inferred from ads, CTAs, or generic copy)
  4. Has a date — a specific date or date range is explicitly stated in the text

Event types: Summit, Dinner, Conference, Roundtable, Meetup, Networking, Happy Hour, Workshop, Forum, Panel, Fireside Chat, Other

EXCLUDE all of the following — when in doubt, EXCLUDE:
  - Webinars, virtual events, online events, livestreams, Zoom/Teams/Meet calls
  - HYBRID events of any kind (in-person + virtual). If the text mentions both physical and online attendance, EXCLUDE.
  - Events whose location is "Online", "Virtual", "Anywhere", "Worldwide", "Global", or similar non-physical descriptor
  - Events that say "join from anywhere", "watch live", "register for free", "stream live"
  - Events that mention a streaming platform, broadcast, or "tune in"
  - Past events (date < {today})
  - Blog posts, case studies, product pages, press releases, job postings
  - Recurring generic meetups with no specific upcoming date
  - Events where you cannot identify a specific physical venue or city — when in doubt, leave it out

━━━ DATE RULES (CRITICAL) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You MUST follow these rules strictly:
  - Extract dates ONLY from what is explicitly written in the text
  - NEVER guess, infer, or fabricate a date
  - If only a month and year are stated (e.g. "June 2026"), use the 1st: "2026-06-01" and set date_source to "partial"
  - If only a quarter is stated (e.g. "Q3 2026"), use the quarter start date and set date_source to "partial"
  - If NO date is found in the text at all, set date to "TBD" and date_source to "none"
  - For LinkedIn posts prefixed with "[LinkedIn post from YYYY-MM-DD]":
    - Relative phrases like "next week", "this Thursday", "tomorrow" refer to dates relative to the POST date, NOT today
    - Calculate the actual date from the post date, then check if it is still upcoming (>= {today}). If not, SKIP the event.
  - date_source values:
    - "explicit" = exact day/month/year stated (e.g. "March 15, 2026", "2026-03-15", "15th March")
    - "partial"  = only month/year or quarter stated
    - "none"     = no date information found in text

━━━ RELEVANCE SCORING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score how relevant the event is for Zenskar, a B2B billing and revenue recognition platform targeting mid-market finance teams.

HIGH (7-10) — Event directly targets our buyers or covers our topics:
  - Audience: CFOs, Controllers, VP/Director/Head of Finance, Head of Accounting, Head of Billing, Head of Revenue, FP&A leaders, RevOps, BizOps, Deal Desk
  - Topics: billing automation, revenue recognition, subscription/usage-based pricing, financial operations, SaaS metrics, ARR/MRR, order-to-cash, collections, invoicing
  - Bonus: B2B SaaS focus, company size 150-2000 employees, US/UK geography

MEDIUM (4-6) — Adjacent audience or tangential topics:
  - General finance professionals, startup founders discussing finance
  - Accounting, tax, audit, compliance professionals
  - Broad fintech or SaaS events with some finance content

LOW (1-3) — Wrong audience or off-topic:
  - Developer/engineering audiences, marketing/sales with no finance angle
  - B2C, consumer, HR, recruiting, legal (unless finance-adjacent)

━━━ RESPONSE FORMAT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond with valid JSON only. No markdown, no explanation, no commentary.

{{
  "is_event": true,
  "events": [
    {{
      "event_name": "exact name as written in source",
      "host_company": "company hosting/organizing the event",
      "event_type": "Summit|Dinner|Conference|Roundtable|Meetup|Networking|Happy Hour|Workshop|Forum|Panel|Fireside Chat|Other",
      "date": "YYYY-MM-DD or TBD",
      "date_source": "explicit|partial|none",
      "location": "City, State/Country — Venue Name",
      "target_audience": "who the event targets",
      "registration_url": "full URL if found, otherwise empty string",
      "description": "1-2 sentence factual summary from the source text",
      "relevance_score": 1
    }}
  ]
}}

If NO qualifying events are found, respond:
{{
  "is_event": false,
  "events": []
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
    return f"""Extract upcoming in-person events from the {len(batch)} page(s) below.
For each event, include a "source_page" integer (1-{len(batch)}) indicating which page it came from.
Return valid JSON only — no commentary.

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
            # Handle truncated JSON (max_tokens hit mid-response)
            finish_reason = response.choices[0].finish_reason
            if finish_reason == "length":
                logger.warning(f"[Classifier] Response truncated in batch {batch_idx+1} — may lose events")
                # Try to salvage: close any open brackets
                result_text = result_text.rstrip()
                if not result_text.endswith("}"):
                    # Attempt to close the JSON structure
                    result_text += ']}' if '"events"' in result_text else '}'
            result = json.loads(result_text)

            events_list = result.get("events", [])
            # Handle both single-page and batch response formats
            if not events_list and result.get("is_event"):
                events_list = []

            for event in events_list:
                # Filter events with no real date (hallucinated or missing)
                date_str = (event.get("date", "") or "").strip()
                date_source = (event.get("date_source", "") or "").lower()
                if date_source == "none" or date_str.upper() in ("TBD", "", "N/A", "UNKNOWN"):
                    print(f"  ⏭ No date: {event.get('event_name', '?')} (date_source: {date_source})")
                    event.pop("date_source", None)
                    continue

                # Strip date_source from output — it's only for filtering
                event.pop("date_source", None)

                # Filter past events
                if _is_past_event(date_str):
                    print(f"  ⏭ Past: {event.get('event_name', '?')} ({date_str})")
                    continue

                # Filter virtual/online/hybrid events that slipped through the LLM
                loc = (event.get("location", "") or "").lower()
                etype = (event.get("event_type", "") or "").lower()
                ename = (event.get("event_name", "") or "").lower()
                desc = (event.get("description", "") or "").lower()
                is_virtual = (
                    any(v in loc for v in VIRTUAL_SIGNALS)
                    or etype in VIRTUAL_EVENT_TYPES
                    or any(v in etype for v in VIRTUAL_SIGNALS)
                    or any(v in ename for v in ["webinar", "virtual", "online event", "livestream", "hybrid"])
                    or any(v in desc for v in VIRTUAL_DESCRIPTION_PHRASES)
                    or not loc or loc in ("tbd", "n/a", "not specified", "unknown", "online", "virtual", "remote")
                )
                if is_virtual:
                    print(f"  🚫 Virtual/Online: {event.get('event_name', '?')} (location: {loc or 'empty'})")
                    continue

                if event.get("relevance_score", 0) >= min_relevance:
                    # Map back to source company from batch using source_page index
                    if not event.get("source_company"):
                        source_page = event.pop("source_page", None)
                        matched = False
                        # Prefer the explicit page index from the LLM
                        if source_page is not None:
                            try:
                                page_idx = int(source_page) - 1
                                if 0 <= page_idx < len(batch):
                                    item = batch[page_idx]
                                    event["source_company"] = item["company"]
                                    event["source_category"] = item["category"]
                                    event["source_url"] = item["source_url"]
                                    matched = True
                            except (ValueError, TypeError):
                                pass
                        # Fallback: fuzzy name matching
                        if not matched:
                            host = event.get("host_company", "").lower()
                            for item in batch:
                                if item["company"].lower() in host or host in item["company"].lower():
                                    event["source_company"] = item["company"]
                                    event["source_category"] = item["category"]
                                    event["source_url"] = item["source_url"]
                                    matched = True
                                    break
                        # Last resort: first item in batch
                        if not matched:
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

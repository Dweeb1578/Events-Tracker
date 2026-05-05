"""
Apollo Enricher
Enriches LinkedIn engagers with contact and company data via the Apollo
People Match API. Respects a configurable credit limit.

API docs: https://apolloio.github.io/apollo-api-docs/
Endpoint: POST /api/v1/people/match
"""

import logging
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

APOLLO_API_URL = "https://api.apollo.io/api/v1/people/match"


def _get_api_key() -> str:
    key = os.getenv("APOLLO_API_KEY")
    if not key:
        raise ValueError(
            "APOLLO_API_KEY not set. Get a free key at https://app.apollo.io/ "
            "→ Settings → Integrations → API Keys"
        )
    return key


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'Jane Smith' into ('Jane', 'Smith')."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name.strip(), ""


def _enrich_single(
    api_key: str,
    linkedin_url: str = "",
    name: str = "",
    company: str = "",
) -> dict | None:
    """
    Call Apollo People Match API for a single person.
    Returns the matched person dict or None on failure.
    """
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "x-api-key": api_key,
    }

    payload = {}
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if name:
        first, last = _split_name(name)
        payload["first_name"] = first
        if last:
            payload["last_name"] = last
    if company:
        payload["organization_name"] = company

    if not payload:
        return None

    try:
        resp = requests.post(APOLLO_API_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code == 429:
            logger.warning("[Apollo] Rate limited — waiting 10s")
            time.sleep(10)
            resp = requests.post(APOLLO_API_URL, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("person") or data.get("match") or data
    except requests.exceptions.HTTPError as e:
        if "422" in str(e):
            logger.debug(f"[Apollo] No match for {name or linkedin_url}")
            return None
        logger.warning(f"[Apollo] HTTP error: {e}")
        return None
    except Exception as e:
        logger.warning(f"[Apollo] Request failed: {e}")
        return None


def _extract_enriched_fields(person: dict) -> dict:
    """Extract relevant fields from Apollo person response."""
    org = person.get("organization") or {}
    return {
        "email": person.get("email", ""),
        "title": person.get("title", ""),
        "company": org.get("name", ""),
        "company_size": org.get("estimated_num_employees", ""),
        "industry": org.get("industry", ""),
        "location": ", ".join(
            filter(None, [
                person.get("city", ""),
                person.get("state", ""),
                person.get("country", ""),
            ])
        ),
        "country": person.get("country", ""),
    }


def enrich_engagers(engagers: list[dict], limit: int = 100) -> list[dict]:
    """
    Enrich engagers with Apollo People Match API data.

    Args:
        engagers: List of engager dicts with linkedin_url, name, parsed_company.
        limit: Maximum number of API calls to make (budget cap).

    Returns:
        The same list with enriched fields added to each engager.
        Engagers that fail enrichment keep their headline-parsed data.
    """
    if limit <= 0:
        print("[Apollo] Enrichment skipped (limit=0)")
        for e in engagers:
            e["enriched"] = False
        return engagers

    try:
        api_key = _get_api_key()
    except ValueError as e:
        print(f"  [Apollo] {e}")
        for e in engagers:
            e["enriched"] = False
        return engagers

    enriched_count = 0
    failed_count = 0
    to_enrich = engagers[:limit]
    remaining = engagers[limit:]

    print(f"\n  [Apollo] Enriching {len(to_enrich)} engagers (limit: {limit})...")

    for i, engager in enumerate(to_enrich):
        person = _enrich_single(
            api_key,
            linkedin_url=engager.get("linkedin_url", ""),
            name=engager.get("name", ""),
            company=engager.get("parsed_company", ""),
        )

        if person and isinstance(person, dict):
            fields = _extract_enriched_fields(person)
            # Only overwrite if Apollo returned a value
            for key, value in fields.items():
                if value:
                    engager[key] = value
            engager["enriched"] = True
            enriched_count += 1
        else:
            engager["enriched"] = False
            failed_count += 1

        # Progress indicator every 10
        if (i + 1) % 10 == 0:
            print(f"    [{i+1}/{len(to_enrich)}] enriched: {enriched_count}, failed: {failed_count}")

        # Rate limit: 1 second between calls
        if i < len(to_enrich) - 1:
            time.sleep(1)

    # Mark remaining (over-limit) engagers as not enriched
    for engager in remaining:
        engager["enriched"] = False

    print(f"  [Apollo] Done: {enriched_count} enriched, {failed_count} failed"
          f"{f', {len(remaining)} skipped (over limit)' if remaining else ''}")

    return engagers

"""
ICP (Ideal Customer Profile) Filter
Two-stage filtering for LinkedIn engagers:
  1. Pre-filter by headline (free, before Apollo enrichment)
  2. Score by enriched data (after Apollo, 0-100 scale)

ICP target: Senior finance leaders (CFO, Controller, VP Finance)
at B2B SaaS companies with 150-1500 employees in US/UK/Canada.
"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Title keywords for ICP match ──
ICP_TITLE_KEYWORDS = [
    "cfo",
    "chief financial officer",
    "chief accounting officer",
    "cao",
    "controller",
    "comptroller",
    "vp finance",
    "vp of finance",
    "vice president finance",
    "vice president of finance",
    "svp finance",
    "evp finance",
    "head of finance",
    "head of billing",
    "head of revenue",
    "head of accounting",
    "head of fp&a",
    "director of finance",
    "director finance",
    "finance director",
    "director of accounting",
    "director of revenue",
    "director of billing",
    "vp accounting",
    "vp revenue",
    "head of business systems",
    "vp revops",
    "director revops",
]

# ── Anti-ICP: titles that are definitely not our target ──
ICP_TITLE_EXCLUDE = [
    "software engineer",
    "senior engineer",
    "staff engineer",
    "developer",
    "marketing manager",
    "marketing director",
    "content marketing",
    "sales rep",
    "sales development",
    "sdr",
    "bdr",
    "recruiter",
    "talent acquisition",
    "designer",
    "ux designer",
    "product manager",
    "product designer",
    "intern",
    "student",
    "looking for",
    "seeking opportunities",
    "open to work",
]

# ── Industry keywords that signal B2B SaaS ──
SAAS_INDUSTRY_KEYWORDS = [
    "software",
    "saas",
    "cloud",
    "platform",
    "technology",
    "information technology",
    "internet",
    "computer software",
    "it services",
]


def pre_filter_engagers(engagers: list[dict]) -> list[dict]:
    """
    Pre-filter engagers by headline before Apollo enrichment.
    Keeps engagers whose title matches ICP keywords, or whose title
    is unparsable (let Apollo decide). Removes obvious non-ICP.

    Returns:
        Filtered list of engagers.
    """
    kept = []
    excluded = 0

    for engager in engagers:
        title = engager.get("parsed_title", "").lower().strip()

        # If no title parsed, keep them — Apollo will clarify
        if not title:
            kept.append(engager)
            continue

        # Check anti-ICP first (reject obvious mismatches)
        if any(kw in title for kw in ICP_TITLE_EXCLUDE):
            excluded += 1
            continue

        # Check ICP match (accept)
        if any(kw in title for kw in ICP_TITLE_KEYWORDS):
            kept.append(engager)
            continue

        # Title exists but doesn't match either list — keep for enrichment
        # (could be an unusual title like "Finance Lead" or "Billing Operations Manager")
        kept.append(engager)

    logger.info(f"ICP pre-filter: {len(engagers)} → {len(kept)} (excluded {excluded} non-ICP)")
    if excluded:
        print(f"  [ICP] Pre-filter excluded {excluded} non-ICP engagers "
              f"(engineers, marketers, recruiters, etc.)")

    return kept


def score_engager(engager: dict) -> int:
    """
    Score an engager for ICP fit (0-100) based on enriched data.

    Components:
      - Title match (0-40)
      - Company size (0-25)
      - Industry (0-20)
      - Geography (0-15)

    Call this AFTER Apollo enrichment has populated title, company_size,
    industry, and location fields.
    """
    score = 0

    # ── Title scoring (0-40) ──
    title = (engager.get("title") or engager.get("parsed_title") or "").lower()
    if any(kw in title for kw in ["cfo", "chief financial officer", "chief accounting officer", "cao"]):
        score += 40
    elif any(kw in title for kw in ["vp finance", "vp of finance", "vice president finance",
                                      "svp finance", "evp finance"]):
        score += 35
    elif any(kw in title for kw in ["controller", "comptroller"]):
        score += 30
    elif any(kw in title for kw in ["head of billing", "head of revenue", "head of finance",
                                      "head of accounting", "head of fp&a",
                                      "head of business systems"]):
        score += 30
    elif any(kw in title for kw in ["director of finance", "finance director",
                                      "director of accounting", "director of billing",
                                      "director of revenue", "vp revops", "director revops"]):
        score += 25
    elif any(kw in title for kw in ["finance", "billing", "revenue", "accounting"]):
        score += 15

    # ── Company size scoring (0-25) ──
    size = engager.get("company_size")
    if size:
        try:
            size_num = int(size) if isinstance(size, (int, str)) else 0
        except (ValueError, TypeError):
            # Handle range strings like "51-200"
            match = re.search(r"(\d+)", str(size))
            size_num = int(match.group(1)) if match else 0

        if 150 <= size_num <= 1500:
            score += 25
        elif 1500 < size_num <= 3000:
            score += 15
        elif 50 <= size_num < 150:
            score += 10

    # ── Industry scoring (0-20) ──
    industry = (engager.get("industry") or "").lower()
    if any(kw in industry for kw in SAAS_INDUSTRY_KEYWORDS):
        score += 20
    elif "financial" in industry or "fintech" in industry:
        score += 15

    # ── Geography scoring (0-15) ──
    location = (engager.get("location") or "").lower()
    country = (engager.get("country") or "").lower()
    geo_str = f"{location} {country}"
    if any(term in geo_str for term in ["united states", "usa", ", us", "u.s."]):
        score += 15
    elif any(term in geo_str for term in ["united kingdom", ", uk", "canada"]):
        score += 12
    elif any(term in geo_str for term in ["israel", "india"]):
        score += 5

    return min(score, 100)

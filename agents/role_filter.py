"""Free pre-enrichment filter: drop tracked-org employees and non-ICP roles. Fails open."""
import re

from agents.icp_filter import ICP_TITLE_EXCLUDE

# "co" is intentionally excluded — it is part of brand names like "Zone & Co"
# and would incorrectly strip meaningful name components. Unambiguous legal
# entity suffixes only.
_SUFFIXES = re.compile(r"\b(inc|llc|ltd|corp|gmbh|plc)\.?\b", re.IGNORECASE)


def normalize_org(name: str) -> str:
    """Lowercase, strip parentheticals + legal suffixes + punctuation for matching."""
    if not name:
        return ""
    n = re.sub(r"\(.*?\)", "", name)          # drop parentheticals
    n = n.replace(",", " ")
    n = _SUFFIXES.sub("", n)
    n = re.sub(r"\s+", " ", n).strip().lower().strip(" .")
    return n


def load_tracked_orgs(companies: list[dict]) -> set[str]:
    """Normalized org-name set to exclude. Pass the flat list from orchestrator.load_companies() (already flattened from companies.yaml)."""
    return {normalize_org(c["name"]) for c in companies if c.get("name")}


def role_prefilter(engagers: list[dict], tracked_orgs: set[str]) -> tuple[list[dict], dict]:
    """Return (kept, counts). counts has 'own_company' and 'non_icp_role'."""
    kept = []
    counts = {"own_company": 0, "non_icp_role": 0}

    for e in engagers:
        company = normalize_org(e.get("parsed_company", ""))
        if company and company in tracked_orgs:
            counts["own_company"] += 1
            continue

        title = (e.get("parsed_title", "") or "").lower().strip()
        if title and any(kw in title for kw in ICP_TITLE_EXCLUDE):
            counts["non_icp_role"] += 1
            continue

        kept.append(e)  # fail open: blank title/company kept for the ICP engine

    return kept, counts

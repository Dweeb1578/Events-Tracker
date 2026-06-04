# LinkedIn Event-Engager ICP Invite Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture likers + commenters of competitor/community LinkedIn event posts, drop tracked-org employees and non-ICP roles for free, then score the rest with the copied `icp_classification/` LLM engine (PDL-first, Apollo fallback), and output a ranked invite list with warm reason, engagement strength, and event metadata.

**Architecture:** A new `agents/engager_pipeline.py` orchestrates: scrape posts → scrape engagers (single Apify actor) → extract + dedup → free role pre-filter → ICP classification via `icp_classification/` → attach extras → write Excel + Sheets. New pure-logic modules are unit-tested; network calls are mocked in tests and guarded behind explicit flags.

**Tech Stack:** Python 3.14, pytest, Apify (REST + `apify-client`), People Data Labs + Apollo (`httpx`/`requests`), Groq LLM (existing), openpyxl + gspread (existing).

**Spec:** `docs/superpowers/specs/2026-06-02-linkedin-engager-icp-pipeline-design.md`

---

## File Structure

| File | Responsibility | New/Mod |
|---|---|---|
| `requirements.txt` | add `httpx`, `apify-client` (used by copied `icp_classification/`) | Mod |
| `icp_classification/.env.example` | document `PDL_API_KEY` | Mod |
| `tests/conftest.py` | put repo root + `icp_classification/` on `sys.path` | New |
| `agents/linkedin_scraper.py` | add `scrape_post_engagers()` (single engagers actor) | Mod |
| `agents/engager_extractor.py` | add `extract_engagers_from_actor()` + composite dedup | Mod |
| `agents/event_meta.py` | parse `event_date` + `event_city` from post text | New |
| `agents/role_filter.py` | own-company + non-ICP role pre-filter (free) | New |
| `icp_classification/pdl_enricher.py` | PDL person enrichment + field mapping | New |
| `icp_classification/enrichment.py` | call PDL first, Apollo fallback | Mod |
| `agents/engager_scoring.py` | `engagement_strength()` + `warm_reason()` | New |
| `agents/engager_pipeline.py` | orchestrate the whole engager flow | New |
| `agents/excel_writer.py` | extra engager columns | Mod |
| `agents/sheets_writer.py` | extra engager columns | Mod |
| `agents/orchestrator.py` | replace step-5 block to call new pipeline | Mod |

---

## Task 0: Project setup — deps, test scaffolding, env docs

**Files:**
- Modify: `requirements.txt`
- Modify: `icp_classification/.env.example`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add missing deps to `requirements.txt`**

Append these two lines (the copied `icp_classification/enrichment.py` imports them):

```
httpx>=0.27.0
apify-client>=1.7.0
```

- [ ] **Step 2: Document the PDL key in `icp_classification/.env.example`**

Append:

```
# People Data Labs — person enrichment (free tier ~1k/mo). Used PDL-first, Apollo fallback.
PDL_API_KEY=
```

- [ ] **Step 3: Create `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 4: Create `tests/conftest.py`** so tests can import both `agents.*` and the copied ICP modules

```python
"""Pytest path setup: make repo root and the copied icp_classification package importable."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICP = os.path.join(ROOT, "icp_classification")

for p in (ROOT, ICP):
    if p not in sys.path:
        sys.path.insert(0, p)
```

- [ ] **Step 5: Verify pytest collects nothing-yet cleanly**

Run: `python -m pytest -q`
Expected: `no tests ran` (exit 5) — confirms collection works without import errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt icp_classification/.env.example tests/__init__.py tests/conftest.py
git commit -m "chore: add engager-pipeline deps and test scaffolding"
```

---

## Task 1: Scrape engagers via the single Apify actor

The actor `scraping_solutions/linkedin-posts-engagers-likers-and-commenters-no-cookies`
returns items shaped: `{type:"likers"|"commenters", url_profile, name, subtitle, post_Link}`.
We normalize each into our engager dict.

**Files:**
- Modify: `agents/linkedin_scraper.py`
- Test: `tests/test_scrape_post_engagers.py`

- [ ] **Step 1: Write the failing test** (normalization is pure; the HTTP call is monkeypatched)

```python
# tests/test_scrape_post_engagers.py
from agents import linkedin_scraper


def test_scrape_post_engagers_normalizes_items(monkeypatch):
    fake_items = [
        {"type": "likers", "url_profile": "https://www.linkedin.com/in/ACoAA111",
         "name": "Jane Doe", "subtitle": "VP Finance at AcmeSaaS",
         "post_Link": "https://www.linkedin.com/posts/orb-activity-1"},
        {"type": "commenters", "url_profile": "https://www.linkedin.com/in/ACoAA222",
         "name": "John Roe", "subtitle": "Controller at Beta Inc",
         "post_Link": "https://www.linkedin.com/posts/orb-activity-1"},
    ]
    monkeypatch.setattr(linkedin_scraper, "_run_engagers_actor", lambda urls, limit: fake_items)

    out = linkedin_scraper.scrape_post_engagers(
        ["https://www.linkedin.com/posts/orb-activity-1"], results_limit=50)

    assert len(out) == 2
    assert out[0] == {
        "name": "Jane Doe",
        "headline": "VP Finance at AcmeSaaS",
        "linkedin_url": "https://www.linkedin.com/in/ACoAA111",
        "engagement_type": "liker",
        "source_post_url": "https://www.linkedin.com/posts/orb-activity-1",
    }
    assert out[1]["engagement_type"] == "commenter"


def test_scrape_post_engagers_skips_blank(monkeypatch):
    fake_items = [{"type": "likers", "url_profile": "", "name": "", "subtitle": "", "post_Link": ""}]
    monkeypatch.setattr(linkedin_scraper, "_run_engagers_actor", lambda urls, limit: fake_items)
    assert linkedin_scraper.scrape_post_engagers(["x"]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scrape_post_engagers.py -v`
Expected: FAIL — `AttributeError: module 'agents.linkedin_scraper' has no attribute 'scrape_post_engagers'`

- [ ] **Step 3: Implement in `agents/linkedin_scraper.py`** (add near the other Apify helpers)

```python
# Single no-cookie actor returning BOTH likers and commenters. $1.10/1k.
ENGAGERS_ACTOR_ID = "scraping_solutions~linkedin-posts-engagers-likers-and-commenters-no-cookies"


def _run_engagers_actor(post_urls: list[str], limit: int) -> list:
    """Call the engagers actor for a batch of post URLs. Returns raw item list."""
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    actor_input = {"urls": post_urls, "resultsLimit": limit}
    url = f"{APIFY_API_BASE}/acts/{ENGAGERS_ACTOR_ID}/runs"
    resp = requests.post(url, json=actor_input, headers=headers, timeout=60)
    resp.raise_for_status()
    run_id = resp.json()["data"]["id"]

    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    for _ in range(36):
        time.sleep(5)
        s = requests.get(status_url, headers=headers, timeout=15).json()["data"]
        if s["status"] == "SUCCEEDED":
            break
        if s["status"] in ("FAILED", "ABORTED", "TIMED-OUT"):
            logger.warning(f"[Engagers] actor {s['status']}")
            return []
    else:
        logger.warning("[Engagers] actor timed out")
        return []

    ds = s["defaultDatasetId"]
    items = requests.get(f"{APIFY_API_BASE}/datasets/{ds}/items", headers=headers, timeout=30)
    items.raise_for_status()
    return items.json()


def scrape_post_engagers(post_urls: list[str], results_limit: int = 100) -> list[dict]:
    """
    Scrape likers + commenters for the given event-post URLs via one actor run.
    Returns normalized engager dicts (one per raw item; dedup happens later).
    """
    if not post_urls:
        return []
    try:
        raw = _run_engagers_actor(post_urls, results_limit)
    except requests.exceptions.HTTPError as e:
        if "402" in str(e) or "Payment" in str(e):
            print("💰 Apify credits exhausted — stopping engager scrape")
            return []
        print(f"✗ Engagers actor HTTP error: {e}")
        return []

    out = []
    for item in raw:
        name = (item.get("name") or "").strip()
        url = (item.get("url_profile") or "").strip()
        if not name or not url:
            continue
        etype = "liker" if str(item.get("type", "")).lower().startswith("lik") else "commenter"
        out.append({
            "name": name,
            "headline": (item.get("subtitle") or "").strip(),
            "linkedin_url": url,
            "engagement_type": etype,
            "source_post_url": (item.get("post_Link") or "").strip(),
        })
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scrape_post_engagers.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/linkedin_scraper.py tests/test_scrape_post_engagers.py
git commit -m "feat: scrape likers+commenters via single Apify engagers actor"
```

---

## Task 2: Extract engagers + composite dedup

Engagers can repeat across posts, and a person who *both* liked and commented may
appear with two different URL forms. Dedup by normalized URL **and** by
`name|company`, keeping the stronger engagement (`commenter` beats `liker`).

**Files:**
- Modify: `agents/engager_extractor.py`
- Test: `tests/test_engager_extract_actor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engager_extract_actor.py
from agents.engager_extractor import extract_engagers_from_actor


def _raw(name, headline, url, etype, post="p1"):
    return {"name": name, "headline": headline, "linkedin_url": url,
            "engagement_type": etype, "source_post_url": post}


def test_parses_headline_into_title_and_company():
    out = extract_engagers_from_actor([_raw("Jane Doe", "VP Finance at AcmeSaaS",
                                            "https://linkedin.com/in/ACoAA1", "liker")])
    assert out[0]["parsed_title"] == "VP Finance"
    assert out[0]["parsed_company"] == "AcmeSaaS"


def test_dedup_by_url_keeps_stronger_engagement():
    rows = [
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1/", "liker"),
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1",  "commenter"),
    ]
    out = extract_engagers_from_actor(rows)
    assert len(out) == 1
    assert out[0]["engagement_type"] == "commenter"  # upgraded


def test_dedup_by_name_company_when_urls_differ():
    rows = [
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/ACoAA1", "liker"),
        _raw("Jane Doe", "VP Finance at AcmeSaaS", "https://linkedin.com/in/jane-doe", "commenter"),
    ]
    out = extract_engagers_from_actor(rows)
    assert len(out) == 1
    assert out[0]["engagement_type"] == "commenter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engager_extract_actor.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_engagers_from_actor'`

- [ ] **Step 3: Implement in `agents/engager_extractor.py`** (reuse existing `_parse_headline`)

```python
_STRENGTH = {"liker": 1, "commenter": 2}


def extract_engagers_from_actor(rows: list[dict]) -> list[dict]:
    """
    Normalize + dedup engagers from scrape_post_engagers() output.
    Dedup key: normalized LinkedIn URL, with name|company as a fallback key so a
    person who both liked and commented (different URL forms) merges once.
    Keeps the stronger engagement_type (commenter > liker).
    """
    by_key: dict[str, dict] = {}
    order: list[str] = []

    def stronger(a: str, b: str) -> str:
        return a if _STRENGTH.get(a, 0) >= _STRENGTH.get(b, 0) else b

    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        headline = (row.get("headline") or "").strip()
        title, company = _parse_headline(headline)
        url = (row.get("linkedin_url") or "").strip()

        url_key = url.rstrip("/").lower() if url else ""
        nc_key = f"{name.lower()}|{company.lower()}" if company else ""

        existing_key = url_key if url_key in by_key else (nc_key if nc_key in by_key else None)
        if existing_key:
            cur = by_key[existing_key]
            cur["engagement_type"] = stronger(cur["engagement_type"], row.get("engagement_type", "liker"))
            continue

        engager = {
            "name": name,
            "linkedin_url": url,
            "headline": headline,
            "parsed_title": title,
            "parsed_company": company,
            "engagement_type": row.get("engagement_type", "liker"),
            "source_post_url": row.get("source_post_url", ""),
        }
        key = url_key or nc_key or f"__noidx_{len(order)}"
        by_key[key] = engager
        if nc_key and nc_key != key:
            by_key[nc_key] = engager  # alias so later URL-less dupes merge
        order.append(key)

    return [by_key[k] for k in order]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engager_extract_actor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/engager_extractor.py tests/test_engager_extract_actor.py
git commit -m "feat: extract+dedup engagers from actor output (commenter>liker merge)"
```

---

## Task 3: Parse event metadata (date + city) from post text

**Files:**
- Create: `agents/event_meta.py`
- Test: `tests/test_event_meta.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_event_meta.py
from agents.event_meta import parse_event_city, parse_event_date


def test_city_nyc_variants():
    assert parse_event_city("Join us for a CFO dinner in NYC next week") == "NYC"
    assert parse_event_city("An intimate roundtable in New York City") == "NYC"


def test_city_sf_variants():
    assert parse_event_city("Wine & finance leaders in San Francisco") == "SF"
    assert parse_event_city("Bay Area happy hour for controllers") == "SF"


def test_city_none_when_absent():
    assert parse_event_city("A virtual webinar for finance teams") == ""


def test_date_iso_and_month():
    assert parse_event_date("RSVP for our event on 2026-07-15") == "2026-07-15"
    assert parse_event_date("Dinner on July 15, 2026 in NYC") == "2026-07-15"


def test_date_none_when_absent():
    assert parse_event_date("Join our CFO dinner soon") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_event_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.event_meta'`

- [ ] **Step 3: Implement `agents/event_meta.py`**

```python
"""Parse event date + city from a LinkedIn post's text. Best-effort, returns '' on miss."""
import re
from datetime import datetime

_CITY_PATTERNS = [
    ("NYC", ["nyc", "new york city", "new york", "manhattan", "brooklyn"]),
    ("SF", ["san francisco", "bay area", " sf ", "soma", "silicon valley"]),
]

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def parse_event_city(text: str) -> str:
    """Return 'NYC', 'SF', or '' based on substring signals (pads spaces to catch ' sf ')."""
    if not text:
        return ""
    t = f" {text.lower()} "
    for label, needles in _CITY_PATTERNS:
        if any(n in t for n in needles):
            return label
    return ""


def parse_event_date(text: str) -> str:
    """Return an ISO date 'YYYY-MM-DD' if a clear date is present, else ''."""
    if not text:
        return ""
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    # "July 15, 2026" / "July 15 2026"
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\b", text)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(1).lower()],
                            int(m.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_event_meta.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/event_meta.py tests/test_event_meta.py
git commit -m "feat: parse event date+city from post text"
```

---

## Task 4: Role pre-filter (own-company + non-ICP role)

Free, runs before any paid enrichment. Drops employees of any org we track and
obvious non-ICP roles. Fails **open** (keeps anyone we can't classify).

**Files:**
- Create: `agents/role_filter.py`
- Test: `tests/test_role_filter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_role_filter.py
from agents.role_filter import normalize_org, role_prefilter


def test_normalize_org_strips_suffixes():
    assert normalize_org("OneBill, Inc.") == "onebill"
    assert normalize_org("Zone & Co (Zone Billing)") == "zone & co"


def test_drops_tracked_org_employee():
    tracked = {"orb", "metronome", "operators guild"}
    engagers = [
        {"name": "A", "parsed_title": "VP Finance", "parsed_company": "Orb"},
        {"name": "B", "parsed_title": "CFO", "parsed_company": "AcmeSaaS"},
    ]
    kept, counts = role_prefilter(engagers, tracked)
    assert [e["name"] for e in kept] == ["B"]
    assert counts["own_company"] == 1


def test_drops_non_icp_role():
    engagers = [
        {"name": "C", "parsed_title": "Software Engineer", "parsed_company": "AcmeSaaS"},
        {"name": "D", "parsed_title": "Controller", "parsed_company": "AcmeSaaS"},
    ]
    kept, counts = role_prefilter(engagers, set())
    assert [e["name"] for e in kept] == ["D"]
    assert counts["non_icp_role"] == 1


def test_fails_open_on_blank_title_and_company():
    engagers = [{"name": "E", "parsed_title": "", "parsed_company": ""}]
    kept, counts = role_prefilter(engagers, {"orb"})
    assert [e["name"] for e in kept] == ["E"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_role_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.role_filter'`

- [ ] **Step 3: Implement `agents/role_filter.py`** (reuse `ICP_TITLE_EXCLUDE` from `icp_filter`)

```python
"""Free pre-enrichment filter: drop tracked-org employees and non-ICP roles. Fails open."""
import re

from agents.icp_filter import ICP_TITLE_EXCLUDE

_SUFFIXES = re.compile(r"\b(inc|llc|ltd|corp|co|gmbh|plc)\.?\b", re.IGNORECASE)


def normalize_org(name: str) -> str:
    """Lowercase, strip parentheticals + legal suffixes + punctuation for matching."""
    if not name:
        return ""
    n = re.sub(r"\(.*?\)", "", name)          # drop parentheticals
    n = n.replace(",", " ")
    n = _SUFFIXES.sub("", n)
    n = re.sub(r"\s+", " ", n).strip().lower().rstrip(" .")
    return n


def load_tracked_orgs(companies: list[dict]) -> set[str]:
    """Build the normalized set of org names to exclude from companies.yaml records."""
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_role_filter.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/role_filter.py tests/test_role_filter.py
git commit -m "feat: free role pre-filter (own-company + non-ICP roles, fail-open)"
```

---

## Task 5: PDL enricher + PDL-first integration

**Files:**
- Create: `icp_classification/pdl_enricher.py`
- Modify: `icp_classification/enrichment.py`
- Test: `tests/test_pdl_enricher.py`

- [ ] **Step 1: Write the failing test** (HTTP mocked)

```python
# tests/test_pdl_enricher.py
import pdl_enricher


PDL_OK = {
    "status": 200,
    "data": {
        "full_name": "Jane Doe",
        "job_title": "VP of Finance",
        "job_company_name": "AcmeSaaS",
        "job_company_size": "201-500",
        "job_company_industry": "computer software",
        "location_name": "New York, New York, United States",
        "location_country": "united states",
        "work_email": "jane@acmesaas.com",
    },
}


def test_map_pdl_person_to_schema():
    out = pdl_enricher.map_pdl_person(PDL_OK["data"])
    assert out["person_title"] == "VP of Finance"
    assert out["company_name"] == "AcmeSaaS"
    assert out["employee_count"] == 350          # midpoint of 201-500
    assert out["industry"] == "computer software"
    assert out["country"] == "united states"
    assert out["email"] == "jane@acmesaas.com"


def test_enrich_via_pdl_returns_none_on_miss(monkeypatch):
    monkeypatch.setenv("PDL_API_KEY", "x")
    monkeypatch.setattr(pdl_enricher, "_pdl_get", lambda params: {"status": 404, "data": None})
    assert pdl_enricher.enrich_via_pdl(linkedin_url="https://linkedin.com/in/ACoAA1") is None


def test_enrich_via_pdl_skips_without_key(monkeypatch):
    monkeypatch.delenv("PDL_API_KEY", raising=False)
    assert pdl_enricher.enrich_via_pdl(name="Jane", company="AcmeSaaS") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pdl_enricher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdl_enricher'`

- [ ] **Step 3: Implement `icp_classification/pdl_enricher.py`**

```python
"""People Data Labs person enrichment (PDL-first). Returns normalized dict or None."""
import os
import re

import httpx

PDL_URL = "https://api.peopledatalabs.com/v5/person/enrich"


def _midpoint(size_range: str) -> int | None:
    """'201-500' -> 350 ; '10001+' -> 10001 ; '' -> None."""
    if not size_range:
        return None
    nums = [int(n) for n in re.findall(r"\d+", size_range.replace(",", ""))]
    if len(nums) == 2:
        return (nums[0] + nums[1]) // 2
    return nums[0] if nums else None


def map_pdl_person(data: dict) -> dict:
    """Map a PDL person record onto the enrichment schema used by classifier._build_company_context."""
    return {
        "source": "pdl",
        "person_name": data.get("full_name", ""),
        "person_title": data.get("job_title", ""),
        "person_headline": data.get("job_title", ""),
        "company_name": data.get("job_company_name", "") or "Unknown",
        "industry": data.get("job_company_industry", "") or "Unknown",
        "employee_count": _midpoint(data.get("job_company_size", "")),
        "location": data.get("location_name", "") or "Unknown",
        "country": data.get("location_country", "") or "Unknown",
        "email": data.get("work_email", "") or data.get("personal_emails", [""])[0] if data.get("personal_emails") else data.get("work_email", ""),
        "enriched": True,
    }


def _pdl_get(params: dict) -> dict:
    """Raw PDL call. Returns {'status': int, 'data': dict|None}."""
    key = os.getenv("PDL_API_KEY", "")
    try:
        r = httpx.get(PDL_URL, params={**params, "min_likelihood": 6},
                      headers={"X-Api-Key": key}, timeout=15)
        body = r.json()
        return {"status": r.status_code, "data": body.get("data")}
    except Exception as e:
        print(f"[pdl] request failed: {e}")
        return {"status": 0, "data": None}


def enrich_via_pdl(linkedin_url: str = "", name: str = "", company: str = "") -> dict | None:
    """Try PDL by profile (preferred) or name+company. Returns mapped dict or None."""
    if not os.getenv("PDL_API_KEY"):
        return None
    params = {}
    if linkedin_url:
        params["profile"] = linkedin_url
    if name:
        params["name"] = name
    if company:
        params["company"] = company
    if not params:
        return None
    res = _pdl_get(params)
    if res["status"] == 200 and res["data"]:
        return map_pdl_person(res["data"])
    return None
```

- [ ] **Step 4: Wire PDL-first into `icp_classification/enrichment.py`**

At the top of the file add the import:

```python
from pdl_enricher import enrich_via_pdl
```

Then inside `enrich_from_linkedin`, immediately after `url = extract_linkedin_url(linkedin_url)` and before the `try:` that scrapes via Apify, insert the PDL-first shortcut:

```python
    # PDL-first: try a single PDL person call (disambiguates by profile URL).
    pdl = enrich_via_pdl(linkedin_url=url)
    if pdl:
        domain = pdl.get("domain")
        if domain:
            pricing = _scrape_pricing_page(domain)
            if pricing:
                pdl["pricing_page_content"] = pricing
        return pdl
    # else fall through to the existing Apify + Apollo path (Apollo fallback)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_pdl_enricher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add icp_classification/pdl_enricher.py icp_classification/enrichment.py tests/test_pdl_enricher.py
git commit -m "feat: PDL-first person enrichment with Apollo fallback"
```

---

## Task 6: Engagement strength + warm reason

**Files:**
- Create: `agents/engager_scoring.py`
- Test: `tests/test_engager_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engager_scoring.py
from agents.engager_scoring import engagement_strength, warm_reason


def test_engagement_strength():
    assert engagement_strength("commenter") == "high (comment)"
    assert engagement_strength("liker") == "medium (reaction)"
    assert engagement_strength("") == "medium (reaction)"


def test_warm_reason_comment_with_city():
    e = {"engagement_type": "commenter", "source_post_company": "Orb",
         "event_city": "NYC", "source_post_preview": "CFO dinner in NYC"}
    assert warm_reason(e) == "Commented on Orb's post about a CFO dinner in NYC (NYC)"


def test_warm_reason_like_without_city():
    e = {"engagement_type": "liker", "source_post_company": "Operators Guild",
         "event_city": "", "source_post_preview": "Finance leaders roundtable"}
    assert warm_reason(e) == "Reacted to Operators Guild's post about a Finance leaders roundtable"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engager_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.engager_scoring'`

- [ ] **Step 3: Implement `agents/engager_scoring.py`**

```python
"""Derive engagement strength + a human 'warm reason' for outreach."""


def engagement_strength(engagement_type: str) -> str:
    """Binary intent signal (single actor can't give reaction sub-types)."""
    return "high (comment)" if engagement_type == "commenter" else "medium (reaction)"


def warm_reason(engager: dict) -> str:
    """One-line personalized hook for whoever sends the invite."""
    verb = "Commented on" if engager.get("engagement_type") == "commenter" else "Reacted to"
    company = engager.get("source_post_company", "") or "a competitor"
    preview = (engager.get("source_post_preview", "") or "").strip().rstrip(".")
    topic = f" about a {preview}" if preview else ""
    city = engager.get("event_city", "")
    suffix = f" ({city})" if city else ""
    return f"{verb} {company}'s post{topic}{suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engager_scoring.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/engager_scoring.py tests/test_engager_scoring.py
git commit -m "feat: engagement strength + warm reason"
```

---

## Task 7: ICP classification adapter

Wrap the copied `enrich_profile` + `classify_company` so the pipeline gets a flat
set of fields merged onto each engager. Keep the ICP import isolated here.

**Files:**
- Create: `agents/icp_adapter.py`
- Test: `tests/test_icp_adapter.py`

- [ ] **Step 1: Write the failing test** (ICP engine functions monkeypatched)

```python
# tests/test_icp_adapter.py
from agents import icp_adapter


def test_classify_engager_merges_fields(monkeypatch):
    monkeypatch.setattr(icp_adapter, "_enrich_profile", lambda url: {
        "company_name": "AcmeSaaS", "industry": "software", "employee_count": 300,
        "location": "New York, US", "person_title": "VP Finance", "email": "j@acmesaas.com"})
    monkeypatch.setattr(icp_adapter, "_classify_company", lambda enriched: {
        "success": True, "weighted_score": 8.6, "verdict": "STRONG ICP FIT",
        "verdict_emoji": "✅", "company_name": "AcmeSaaS"})

    e = {"name": "Jane", "linkedin_url": "https://linkedin.com/in/ACoAA1",
         "parsed_title": "VP Finance", "parsed_company": "AcmeSaaS"}
    out = icp_adapter.classify_engager(e)

    assert out["icp_score"] == 86            # 8.6/10 -> 0-100 scale
    assert out["verdict"] == "STRONG ICP FIT"
    assert out["company"] == "AcmeSaaS"
    assert out["title"] == "VP Finance"
    assert out["email"] == "j@acmesaas.com"


def test_classify_engager_handles_failure(monkeypatch):
    monkeypatch.setattr(icp_adapter, "_enrich_profile", lambda url: {"error": "no match"})
    monkeypatch.setattr(icp_adapter, "_classify_company", lambda enriched: {"success": False, "error": "x"})
    e = {"name": "Jane", "linkedin_url": "u", "parsed_title": "VP Finance", "parsed_company": "AcmeSaaS"}
    out = icp_adapter.classify_engager(e)
    assert out["icp_score"] == 0
    assert out["verdict"] == "ERROR"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_icp_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.icp_adapter'`

- [ ] **Step 3: Implement `agents/icp_adapter.py`**

```python
"""Adapter around the copied icp_classification engine. Isolates the sys.path import."""
import os
import sys

_ICP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icp_classification")
if _ICP not in sys.path:
    sys.path.insert(0, _ICP)

from enrichment import enrich_profile as _enrich_profile      # noqa: E402
from classifier import classify_company as _classify_company  # noqa: E402


def classify_engager(engager: dict) -> dict:
    """
    Enrich + classify one engager via the ICP engine; merge results onto the dict.
    Score is converted from the engine's 0-10 weighted_score to a 0-100 icp_score
    (matches the colour thresholds the writers already use: >=70 green, >=50 amber).
    """
    url = engager.get("linkedin_url", "")
    enriched = _enrich_profile(url) if url else {"error": "no url"}
    result = _classify_company(enriched)

    if not result.get("success"):
        engager["icp_score"] = 0
        engager["verdict"] = "ERROR"
        engager["enriched"] = False
        return engager

    engager["icp_score"] = int(round(result.get("weighted_score", 0) * 10))
    engager["verdict"] = result.get("verdict", "")
    engager["company"] = enriched.get("company_name", "") or engager.get("parsed_company", "")
    engager["title"] = enriched.get("person_title", "") or engager.get("parsed_title", "")
    engager["email"] = enriched.get("email", "")
    engager["company_size"] = enriched.get("employee_count", "")
    engager["industry"] = enriched.get("industry", "")
    engager["location"] = enriched.get("location", "")
    engager["enriched"] = True
    return engager
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_icp_adapter.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/icp_adapter.py tests/test_icp_adapter.py
git commit -m "feat: ICP classification adapter (0-10 -> 0-100, field merge)"
```

---

## Task 8: Pipeline orchestration

Tie it together: posts (with text) → engagers → extract/dedup → attach event meta
→ role filter → classify → attach strength/warm-reason → sort.

**Files:**
- Create: `agents/engager_pipeline.py`
- Test: `tests/test_engager_pipeline.py`

- [ ] **Step 1: Write the failing test** (all network/LLM steps monkeypatched)

```python
# tests/test_engager_pipeline.py
from agents import engager_pipeline as ep


def test_pipeline_filters_classifies_and_sorts(monkeypatch):
    posts = [{"source_post_url": "p1", "source_post_company": "Orb",
              "post_text": "CFO dinner in NYC on 2026-07-15", "category": "billing"}]

    monkeypatch.setattr(ep, "scrape_post_engagers", lambda urls, results_limit=100: [
        {"name": "Jane Doe", "headline": "VP Finance at AcmeSaaS",
         "linkedin_url": "https://linkedin.com/in/ACoAA1", "engagement_type": "commenter",
         "source_post_url": "p1"},
        {"name": "Eng Person", "headline": "Software Engineer at AcmeSaaS",
         "linkedin_url": "https://linkedin.com/in/ACoAA2", "engagement_type": "liker",
         "source_post_url": "p1"},
        {"name": "Orb Staff", "headline": "AE at Orb",
         "linkedin_url": "https://linkedin.com/in/ACoAA3", "engagement_type": "liker",
         "source_post_url": "p1"},
    ])

    def fake_classify(e):
        e["icp_score"] = 86
        e["verdict"] = "STRONG ICP FIT"
        e["company"] = e["parsed_company"]
        e["title"] = e["parsed_title"]
        return e
    monkeypatch.setattr(ep, "classify_engager", fake_classify)

    out = ep.run_engager_pipeline(posts, tracked_orgs={"orb"})

    # engineer dropped (non-ICP role), Orb staff dropped (own company) -> only Jane
    assert len(out) == 1
    j = out[0]
    assert j["name"] == "Jane Doe"
    assert j["event_city"] == "NYC"
    assert j["event_date"] == "2026-07-15"
    assert j["engagement_strength"] == "high (comment)"
    assert "Orb" in j["warm_reason"]
    assert j["source_post_company"] == "Orb"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engager_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.engager_pipeline'`

- [ ] **Step 3: Implement `agents/engager_pipeline.py`**

```python
"""Orchestrates the engager flow: scrape → dedup → meta → role filter → ICP → extras → sort."""
import logging

from agents.linkedin_scraper import scrape_post_engagers
from agents.engager_extractor import extract_engagers_from_actor
from agents.event_meta import parse_event_city, parse_event_date
from agents.role_filter import role_prefilter
from agents.icp_adapter import classify_engager
from agents.engager_scoring import engagement_strength, warm_reason

logger = logging.getLogger(__name__)


def run_engager_pipeline(posts: list[dict], tracked_orgs: set[str],
                         results_limit: int = 100) -> list[dict]:
    """
    posts: dicts with source_post_url, source_post_company, post_text, category.
    Returns engager dicts sorted by icp_score desc.
    """
    if not posts:
        return []

    # index post metadata by URL
    meta = {}
    for p in posts:
        url = p.get("source_post_url", "")
        meta[url] = {
            "source_post_company": p.get("source_post_company", ""),
            "source_post_category": p.get("category", ""),
            "source_post_preview": (p.get("post_text", "") or "")[:100].strip(),
            "event_city": parse_event_city(p.get("post_text", "")),
            "event_date": parse_event_date(p.get("post_text", "")),
        }

    post_urls = [p["source_post_url"] for p in posts if p.get("source_post_url")]
    raw = scrape_post_engagers(post_urls, results_limit=results_limit)
    engagers = extract_engagers_from_actor(raw)
    print(f"  [Engagers] {len(engagers)} unique after dedup")

    # attach post-level metadata
    for e in engagers:
        e.update(meta.get(e.get("source_post_url", ""), {}))

    kept, counts = role_prefilter(engagers, tracked_orgs)
    print(f"  [Engagers] role filter dropped {counts['own_company']} own-company, "
          f"{counts['non_icp_role']} non-ICP roles → {len(kept)} to classify")

    classified = []
    for e in kept:
        e = classify_engager(e)
        e["engagement_strength"] = engagement_strength(e.get("engagement_type", ""))
        e["warm_reason"] = warm_reason(e)
        classified.append(e)

    classified.sort(key=lambda x: x.get("icp_score", 0), reverse=True)
    return classified
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engager_pipeline.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add agents/engager_pipeline.py tests/test_engager_pipeline.py
git commit -m "feat: engager pipeline orchestration"
```

---

## Task 9: Add new engager columns to the writers

**Files:**
- Modify: `agents/excel_writer.py` (`ENGAGER_COLUMNS` + row build in `write_engagers`)
- Modify: `agents/sheets_writer.py` (`ENGAGER_HEADERS`, `ENGAGER_COL_WIDTHS`, row build in `write_engagers_to_sheet`)
- Test: `tests/test_writer_columns.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_writer_columns.py
from agents import excel_writer
from agents import sheets_writer


def test_excel_engager_columns_include_new_fields():
    for col in ("Verdict", "Engagement Strength", "Event Date", "Event City", "Warm Reason"):
        assert col in excel_writer.ENGAGER_COLUMNS


def test_sheets_engager_headers_include_new_fields():
    for col in ("Verdict", "Engagement Strength", "Event Date", "Event City", "Warm Reason"):
        assert col in sheets_writer.ENGAGER_HEADERS


def test_excel_writes_engager_rows(tmp_path):
    out = tmp_path / "e.xlsx"
    n = excel_writer.write_engagers([{
        "name": "Jane Doe", "linkedin_url": "https://linkedin.com/in/ACoAA1",
        "title": "VP Finance", "company": "AcmeSaaS", "icp_score": 86,
        "verdict": "STRONG ICP FIT", "engagement_type": "commenter",
        "engagement_strength": "high (comment)", "event_date": "2026-07-15",
        "event_city": "NYC", "warm_reason": "Commented on Orb's post (NYC)",
        "source_post_url": "p1", "source_post_company": "Orb",
    }], output_path=str(out))
    assert n == 1 and out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writer_columns.py -v`
Expected: FAIL — assertion error (new columns not present yet)

- [ ] **Step 3a: Update `agents/excel_writer.py`**

Replace the `ENGAGER_COLUMNS` list (currently lines ~355-370) with:

```python
ENGAGER_COLUMNS = [
    "Name",
    "LinkedIn URL",
    "Title",
    "Company",
    "Email",
    "Company Size",
    "Industry",
    "Location",
    "ICP Score",
    "Verdict",
    "Engagement Type",
    "Engagement Strength",
    "Event Date",
    "Event City",
    "Warm Reason",
    "Source Post",
    "Source Company",
    "Enriched At",
]
```

Add widths for the new columns inside the `_set_column_widths(...)` call in `write_engagers`:

```python
        _set_column_widths(ws, {
            "Name": 22, "LinkedIn URL": 40, "Title": 25,
            "Company": 22, "Email": 30, "Company Size": 14,
            "Industry": 20, "Location": 22, "ICP Score": 10,
            "Verdict": 16, "Engagement Type": 14, "Engagement Strength": 16,
            "Event Date": 12, "Event City": 10, "Warm Reason": 50,
            "Source Post": 40, "Source Company": 18, "Enriched At": 20,
        }, ENGAGER_COLUMNS)
```

Replace the `row_data` list in `write_engagers` (currently lines ~416-431) with:

```python
        row_data = [
            engager.get("name", ""),
            linkedin_url,
            engager.get("title", "") or engager.get("parsed_title", ""),
            engager.get("company", "") or engager.get("parsed_company", ""),
            engager.get("email", ""),
            engager.get("company_size", ""),
            engager.get("industry", ""),
            engager.get("location", ""),
            engager.get("icp_score", 0),
            engager.get("verdict", ""),
            engager.get("engagement_type", ""),
            engager.get("engagement_strength", ""),
            engager.get("event_date", ""),
            engager.get("event_city", ""),
            engager.get("warm_reason", ""),
            engager.get("source_post_url", ""),
            engager.get("source_post_company", ""),
            now,
        ]
```

- [ ] **Step 3b: Update `agents/sheets_writer.py`**

Replace `ENGAGER_HEADERS` (line ~578) and `ENGAGER_COL_WIDTHS` (line ~595) with:

```python
ENGAGER_HEADERS = [
    "Name", "LinkedIn URL", "Title", "Company", "Email", "Company Size",
    "Industry", "Location", "ICP Score", "Verdict", "Engagement Type",
    "Engagement Strength", "Event Date", "Event City", "Warm Reason",
    "Source Post", "Source Company", "Enriched At",
]
ENGAGER_COL_WIDTHS = [180, 200, 180, 180, 220, 100, 150, 170, 80, 140, 110,
                      150, 100, 90, 320, 200, 140, 140]
```

Then locate the row assembly in `write_engagers_to_sheet` (the list comprehension building `rows` before `ws.append_rows(rows, ...)` at ~line 816) and make each row match the new header order:

```python
    rows = [[
        e.get("name", ""),
        e.get("linkedin_url", ""),
        e.get("title", "") or e.get("parsed_title", ""),
        e.get("company", "") or e.get("parsed_company", ""),
        e.get("email", ""),
        e.get("company_size", ""),
        e.get("industry", ""),
        e.get("location", ""),
        e.get("icp_score", 0),
        e.get("verdict", ""),
        e.get("engagement_type", ""),
        e.get("engagement_strength", ""),
        e.get("event_date", ""),
        e.get("event_city", ""),
        e.get("warm_reason", ""),
        e.get("source_post_url", ""),
        e.get("source_post_company", ""),
        now,
    ] for e in engagers]
```

> Note: `ENGAGER_SCORE_COL` is computed via `ENGAGER_HEADERS.index("ICP Score")`, so the score-colour conditional formatting auto-tracks the new column order — no change needed there. If a `now` variable isn't already defined in this function, add `now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")` near the top of the function (import already present).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writer_columns.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add agents/excel_writer.py agents/sheets_writer.py tests/test_writer_columns.py
git commit -m "feat: add verdict/engagement/event/warm-reason columns to engager output"
```

---

## Task 10: Wire the new pipeline into the orchestrator

Replace the step-5 block in `agents/orchestrator.py` (lines ~303-378) so
`--extract-engagers` runs the new pipeline. The post source is the existing
keyword-matched LinkedIn event posts (we reuse `scrape_posts_with_comments` only
to *find* event posts + their text/URLs; engager scraping uses the new actor).

**Files:**
- Modify: `agents/orchestrator.py`
- Test: `tests/test_orchestrator_engager_wiring.py`

- [ ] **Step 1: Write the failing test** (pipeline + scraping monkeypatched; assert the wiring calls through)

```python
# tests/test_orchestrator_engager_wiring.py
from agents import orchestrator


def test_run_engager_stage_calls_pipeline(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(orchestrator, "scrape_posts_with_comments", lambda sources: [
        {"source_post_url": "p1", "source_post_company": "Orb",
         "post_text": "CFO dinner in NYC", "category": "billing"}])

    def fake_pipeline(posts, tracked_orgs, results_limit=100):
        captured["posts"] = posts
        captured["tracked"] = tracked_orgs
        return [{"name": "Jane", "icp_score": 86, "verdict": "STRONG ICP FIT"}]
    monkeypatch.setattr(orchestrator, "run_engager_pipeline", fake_pipeline)

    written = {}
    monkeypatch.setattr(orchestrator, "write_engagers",
                        lambda eng, output_path, dry_run=False: written.setdefault("n", len(eng)))

    sources = [{"company": "Orb", "category": "billing",
                "linkedin_url": "https://linkedin.com/company/orbhq"}]
    n = orchestrator.run_engager_stage(sources, output_path=str(tmp_path / "o.xlsx"),
                                       sheet_id=None, dry_run=False)

    assert n == 1
    assert "orb" in captured["tracked"]
    assert captured["posts"][0]["source_post_company"] == "Orb"
    assert written["n"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_orchestrator_engager_wiring.py -v`
Expected: FAIL — `AttributeError: module 'agents.orchestrator' has no attribute 'run_engager_stage'`

- [ ] **Step 3: Refactor the step-5 block into `run_engager_stage` in `agents/orchestrator.py`**

Add these imports near the top of the file (with the other `from agents...` imports):

```python
from agents.engager_pipeline import run_engager_pipeline
from agents.role_filter import load_tracked_orgs
```

Add the function (place it above `run_pipeline`):

```python
def run_engager_stage(engager_sources: list[dict], output_path: str,
                      sheet_id: str | None, dry_run: bool) -> int:
    """Find event posts among sources, run the engager pipeline, write results."""
    from agents.linkedin_scraper import scrape_posts_with_comments

    # Reuse the comment scraper purely to surface keyword-matched event posts + text.
    posts_raw = scrape_posts_with_comments(engager_sources)
    posts = [{
        "source_post_url": p.get("source_post_url", ""),
        "source_post_company": p.get("source_post_company", ""),
        "post_text": p.get("post_text", ""),
        "category": p.get("source_post_category", ""),
    } for p in posts_raw if p.get("source_post_url")]

    if not posts:
        print("   No event posts found for engager extraction")
        return 0

    tracked = load_tracked_orgs(load_companies())
    engagers = run_engager_pipeline(posts, tracked_orgs=tracked)
    if not engagers:
        print("   No ICP engagers after filtering")
        return 0

    top = [e.get("icp_score", 0) for e in engagers[:5]]
    print(f"   Top 5 ICP scores: {top}")

    count = write_engagers(engagers, output_path=output_path, dry_run=dry_run)
    if sheet_id:
        try:
            write_engagers_to_sheet(engagers, sheet_id=sheet_id, dry_run=dry_run)
        except Exception as e:
            logger.error(f"[Sheets] Failed to write engagers: {e}")
            print(f"  ⚠️  Google Sheets engager write failed: {e}")
    return count
```

Then replace the body of the `if extract_engagers:` block (lines ~305-378) with a thin caller:

```python
    engager_count = 0
    if extract_engagers:
        print("\n" + "=" * 60)
        print("👥 STEP 5: Engager Extraction Pipeline")
        print("=" * 60)
        try:
            all_companies = load_companies(config_path) if config_path else load_companies()
            engager_sources = [
                {"company": c["name"], "category": c["category"], "linkedin_url": c["linkedin_url"]}
                for c in all_companies if c.get("linkedin_url")
            ]
            engager_count = run_engager_stage(
                engager_sources, output_path=output_path, sheet_id=sheet_id, dry_run=dry_run)
        except Exception as e:
            logger.error(f"[Engagers] Pipeline failed: {e}", exc_info=True)
            print(f"\n  ⚠️  Engager extraction failed: {e}")
```

> The now-unused imports inside the old block (`apollo_enricher`, `icp_filter.score_engager`, `pre_filter_engagers`, `extract_engagers as do_extract_engagers`) can be removed. `apollo_limit` is no longer used by this stage — leave the CLI arg in place for backward compat but it no longer affects engager scoring (PDL/Apollo limits live in the ICP engine).

- [ ] **Step 4: Run the wiring test + full suite**

Run: `python -m pytest tests/test_orchestrator_engager_wiring.py -v`
Expected: PASS (1 test)

Run: `python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/orchestrator.py tests/test_orchestrator_engager_wiring.py
git commit -m "feat: wire --extract-engagers to new engager pipeline"
```

---

## Task 11: End-to-end smoke test (manual, costs credits)

**Files:** none (manual validation)

- [ ] **Step 1: Ensure keys present**

Confirm `.env` has `APIFY_API_TOKEN`, `GROQ_API_KEY`, `APOLLO_API_KEY`. Add
`PDL_API_KEY` when available (pipeline runs without it — Apollo fallback).

- [ ] **Step 2: Run a real, scoped extraction**

Run: `python main.py --extract-engagers --dry-run`
Expected: console shows posts found → engagers deduped → role-filter drop counts
→ top-5 ICP scores → dry-run rows. No file writes on dry-run.

- [ ] **Step 3: Run for real and inspect output**

Run: `python main.py --extract-engagers`
Open `output/events.xlsx` → "Engagers" sheet. Verify: rows sorted by ICP score,
own-company/competitor employees absent, warm reason + event city populated.

- [ ] **Step 4: Commit any fixups discovered during smoke test** (if needed)

---

## Self-Review

**Spec coverage:**
- Likers + commenters → Task 1. ✓
- Role pre-filter (own/competitor/community + non-ICP role) → Task 4 + tracked orgs from `companies.yaml` in Task 10. ✓
- LLM ICP engine reuse → Task 7. ✓
- PDL-first, Apollo fallback → Task 5. ✓
- Warm reason, engagement strength, event metadata → Tasks 3, 6, 8. ✓
- Output ranked + new columns → Task 9; sort in Task 8. ✓
- Encoded URLs used as-is → Tasks 1/2 (no decode). ✓
- Graceful degradation w/o PDL key → Task 5 (`enrich_via_pdl` returns None → Apollo path). ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type/name consistency:** `scrape_post_engagers` (Task 1) consumed in Tasks 8/10; `extract_engagers_from_actor` (Task 2) used in Task 8; `role_prefilter`/`load_tracked_orgs` (Task 4) used in Tasks 8/10; `classify_engager` (Task 7) used in Task 8; `engagement_strength`/`warm_reason` (Task 6) used in Task 8; `run_engager_pipeline` (Task 8) used in Task 10. Engager dict keys (`icp_score`, `verdict`, `engagement_strength`, `event_date`, `event_city`, `warm_reason`, `company`, `title`, `email`, `company_size`, `industry`, `location`, `source_post_url`, `source_post_company`) are produced in Tasks 7/8 and consumed by the writers in Task 9. ✓

**Note on `scrape_posts_with_comments` reuse (Task 10):** it must expose `post_text` and `source_post_url` per matched post — it already returns `post_text` and `source_post_url` (see `agents/linkedin_scraper.py` `scrape_posts_with_comments`). If a future change drops those keys, Task 10's `posts` mapping must be updated accordingly.
```

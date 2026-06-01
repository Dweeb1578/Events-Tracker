# LinkedIn Event-Engager → ICP Invite Pipeline — Design

**Date:** 2026-06-02
**Status:** Approved for planning
**Author:** Vrishab (with Claude)

## Problem

Competitors (Orb, Metronome) and finance communities (Operators Guild, Finance
Alliance, CFO Leadership Council) host frequent in-person dinners/roundtables in
NY and SF. People who engage with those event posts on LinkedIn are
self-selected as interested in finance-leader events — a warm audience for
Zenskar's own events. We want to find those engagers, keep only the ones who
match Zenskar's ICP, and produce a ranked invite list with a personalized
"warm reason" for each.

The existing Events repo already scrapes competitor/community LinkedIn posts and
extracts *commenters*. This project extends that to also capture *reactors
(likers)*, adds a free role pre-filter, and replaces the crude keyword ICP
scorer with the dedicated LLM-based ICP engine that now lives in
`icp_classification/` (copied from the standalone Zenskar ICP Classification
project — the original is left untouched).

## Goals

1. Capture **both likers and commenters** of keyword-matched event posts.
2. **Role pre-filter** (free, pre-enrichment) that drops:
   a. employees of any org we already track in `config/companies.yaml`
      (competitors + communities — they are not prospects), and
   b. obvious non-ICP roles (engineers, recruiters, marketers, sales, etc.).
3. Run survivors through the **LLM ICP engine** (`icp_classification/`) for an
   accurate 0–10 weighted score + verdict.
4. **PDL-first, Apollo-later** enrichment, disambiguating by LinkedIn profile to
   avoid name-collision errors (e.g. "Harvey" the AI startup vs "Harvey Nash").
5. Output a ranked invite list with **warm reason**, **engagement strength**,
   and **event metadata** (date + city).

## Non-Goals

- Sending the invites (out of scope; this produces the list only).
- HubSpot dedup against existing CRM contacts (deferred; not selected for v1).
- Granular reaction-type weighting (love/insightful/like). The chosen single
  actor only distinguishes commenter vs liker, so engagement strength is binary.
- Quoting comment text in the warm reason (single actor returns no comment text).

## Key Decisions (resolved during brainstorming)

| Decision | Choice | Why |
|---|---|---|
| Engager source | Single actor `scraping_solutions/linkedin-posts-engagers-likers-and-commenters` ($1.10/1k, no cookies) | One run for likers+commenters; cheaper/simpler than two harvestapi actors. **Tested live — works.** |
| Profile URL form | Use the encoded `/in/ACoAA…` URL as-is | **Tested:** encoded URLs resolve fine through the profile scraper; no decoding needed. Also used as dedup key. |
| ICP scoring | Reuse `icp_classification/` LLM engine (5 weighted dims + disqualifiers) | Far stronger than keyword scoring; already built and proven. |
| Repo coupling | Import `icp_classification/` as a package; keep per-engager metadata attached | Preserves warm-reason/event/engagement metadata while delegating enrichment + scoring. |
| Enrichment order | PDL first (by profile URL), Apollo fallback on miss | Cheaper (free ~1k/mo) and more accurate disambiguation than Apollo name search. |
| Own-company filter scope | All orgs in `companies.yaml` (competitors + communities) | A Metronome employee reacting to Orb's post is also not ICP. List already exists. |

## Architecture

```
[Events repo]
 1. scrape event posts        agents/linkedin_scraper.py  (harvestapi company-posts, comments OFF)
 2. keyword-filter posts      ENGAGER_KEYWORDS (existing)
 3. parse event metadata      NEW: event_date, event_city from post text
 4. scrape engagers           NEW: single engagers actor → likers + commenters
 5. extract + dedup           agents/engager_extractor.py (extended)
 6. ROLE PRE-FILTER (free)    NEW: agents/role_filter.py
 7. ICP classification        icp_classification/ enrich_profile() + classify_company()
 8. attach extras             engagement_strength, warm_reason, event metadata
 9. write output              Excel + Google Sheets, sorted by weighted_score
```

Orchestrated by a new `agents/engager_pipeline.py` invoked from the existing
`--extract-engagers` flag in `main.py` / `agents/orchestrator.py`.

## Components

### NEW `agents/role_filter.py`
Free, headline-based pre-filter run before any paid enrichment.

- `load_tracked_orgs(companies_yaml_path) -> set[str]`
  Normalized set of every `name` in `companies.yaml` (competitors + communities),
  plus simple variants (lowercase, strip "Inc/LLC/& Co", etc.).
- `is_own_company(engager, tracked_orgs) -> bool`
  True if the engager's `parsed_company` (from the actor `subtitle`) matches a
  tracked org. Matched engagers are dropped.
- `is_non_icp_role(engager) -> bool`
  Reuses the existing `ICP_TITLE_EXCLUDE` list in `agents/icp_filter.py`
  (engineer/recruiter/marketer/sales/designer/PM/student/etc.).
- `role_prefilter(engagers, tracked_orgs) -> (kept, dropped_counts)`
  Applies both; returns survivors plus a breakdown for logging. Unparsable
  company/title are **kept** (let the ICP engine decide) — fail-open, not closed.

### MODIFIED `agents/linkedin_scraper.py`
- Add `scrape_post_engagers(post_urls, results_limit) -> list[dict]` calling the
  single engagers actor. Each result normalized to:
  `{name, headline (=subtitle), linkedin_url (encoded), engagement_type
   (liker|commenter), source_post_url}`.
- Company-post scraping no longer needs `scrapeComments=True` for this path
  (we only need post URLs + text), reducing cost.

### MODIFIED `agents/engager_extractor.py`
- Parse the engagers-actor shape (`name`, `subtitle`, `url_profile`, `type`).
- Reuse `_parse_headline()` on `subtitle` → `parsed_title`, `parsed_company`.
- Dedup: primary key = normalized encoded URL; **composite fallback key =
  `name|parsed_company`** so a person who both liked and commented (encoded URL
  vs vanity URL) is merged once, keeping the strongest `engagement_type`.
- Carry `engagement_type` and `source_post_url` through.

### NEW event-metadata parsing (in `engager_extractor.py` or a small helper)
- From post text: `event_date` (reuse `_parse_post_date` patterns + inline date
  mentions) and `event_city` (substring match on a small NY/SF/region vocab).
- Attached to each engager via its `source_post_url`.

### MODIFIED `icp_classification/enrichment.py` — PDL-first
- New `enrich_via_pdl(linkedin_url, name, company) -> dict | None` using the PDL
  Person Enrichment API. Prefer `profile` (LinkedIn URL) for disambiguation;
  fall back to `name` + `company`. Map PDL fields → the existing normalized
  schema (`company_name`, `industry`, `employee_count`, `location`, `country`,
  `person_title`, etc.).
- In `enrich_from_linkedin` / `enrich_profile`: try PDL first; if PDL misses or
  returns low-confidence, fall back to the current Apollo + Apify path.
- Requires `PDL_API_KEY` in `.env`. If absent, log once and skip straight to the
  Apollo path (graceful degradation — pipeline still works without PDL).

### NEW `agents/engager_pipeline.py`
Orchestrates steps 4–9: takes keyword-matched event posts (URLs + text), scrapes
engagers, extracts/dedups, role-filters, classifies via `icp_classification/`,
attaches extras, returns ranked engager dicts. Keeps the `icp_classification`
import isolated to this module (`sys.path` insert or package import).

### MODIFIED writers (`agents/excel_writer.py`, `agents/sheets_writer.py`)
New columns: `icp_score`, `verdict`, `engagement_type`, `engagement_strength`,
`event_date`, `event_city`, `warm_reason`, plus the existing identity fields.
Sort by `icp_score` desc.

## Data Flow (one engager)

```
{name:"Jane Doe", subtitle:"VP Finance at AcmeSaaS", url_profile:"/in/ACoAA…",
 type:"commenter", source_post_url:"…orb…CFO dinner NYC…"}
   → parse_headline → parsed_title:"VP Finance", parsed_company:"AcmeSaaS"
   → role_filter: AcmeSaaS not in companies.yaml ✓, VP Finance not excluded ✓ → KEEP
   → enrich_profile("/in/ACoAA…"): PDL by profile URL → company AcmeSaaS, 300 emp, SaaS, US
   → classify_company → 8.6/10 ✅ STRONG ICP FIT
   → attach: engagement_strength="high (comment)", event_city="NYC",
             warm_reason="Commented on Orb's 'CFO dinner in NYC' post"
   → row in output, sorted near top
```

## Error Handling

- **Missing PDL key:** log once, skip PDL, use Apollo path. No crash.
- **Actor failure / Apify 402 (credits):** stop engager scraping, keep what we
  have, continue to enrichment (mirrors existing `linkedin_scraper.py` behavior).
- **Enrichment miss for a person:** keep them with headline-only data and a
  neutral score; mark `enriched=False` so they sort below confirmed matches.
- **LLM JSON parse failure:** existing `classify_company` already returns a
  structured error; that engager is logged and skipped, not fatal.
- **Fail-open filtering:** unparsable company/title are kept for the ICP engine
  to judge, so we never silently drop a potential prospect on a parse miss.

## Testing

- Unit: `role_filter` (own-company match incl. variants; non-ICP role drop;
  fail-open on blanks); `engager_extractor` composite dedup (liker+commenter
  merge); event-metadata parsing (date + city extraction).
- Unit: PDL field mapping (mock PDL response → normalized schema) and
  PDL→Apollo fallback selection (mock PDL miss).
- Integration (manual, low cost): one event post → full pipeline → inspect a
  handful of rows for correct score/verdict/warm_reason. Guard live API calls
  behind an explicit flag to avoid burning credits in CI.

## Cost (rough, per weekly run)

- Company-post scrape: existing, ~$ small.
- Engagers actor: ~$1.10/1k engagers; a few event posts × low-hundreds each ≈
  single-digit dollars.
- PDL: free tier (~1k/mo) covers post-role-filter survivors; Apollo only for
  PDL misses → conserves Apollo credits.
- Groq: cheap per classification.

## Open Items

- **`PDL_API_KEY`** to be provided and added to `.env` (free tier signup). Build
  proceeds without it; PDL path is dormant until the key exists.
- Decide later whether PDL fully **replaces** the Apify person-scrape (one PDL
  call returns person + company) or only **precedes** Apollo for the company
  lookup. v1: PDL precedes Apollo; Apify person-scrape stays as the resolver for
  the person's title (already proven to resolve encoded URLs).
- Housekeeping: the copy brought along `bot.py`, `debug_apollo*.py`,
  `GEO-AUDIT-REPORT.md`, tests — prune anything unused once integration settles.
```

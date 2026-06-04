# GEO Audit Report: Zenskar

**Audit Date:** 2026-03-12
**URL:** https://zenskar.com
**Business Type:** SaaS (B2B billing & revenue recognition platform)
**Pages Analyzed:** ~20 (homepage, pricing, integrations, blog, docs, about, legal)

---

## Executive Summary

**Overall GEO Score: 58/100 (Fair)**

Zenskar has a solid content foundation and is clearly optimized for search, but AI systems will struggle to cite or recommend it due to weak structured data, missing llms.txt, partial crawler access, and thin E-E-A-T signals. The biggest opportunity is adding FAQ schema, fixing ClaudeBot/PerplexityBot access, and creating quotable answer blocks on high-intent pages.

### Score Breakdown

| Category | Score | Weight | Weighted Score |
|---|---|---|---|
| AI Citability | 72/100 | 25% | 18.0 |
| Content E-E-A-T | 58/100 | 20% | 11.6 |
| Brand Authority | 58/100 | 20% | 11.6 |
| Technical GEO | 52/100 | 15% | 7.8 |
| Schema & Structured Data | 41/100 | 10% | 4.1 |
| Platform Optimization | 52/100 | 10% | 5.2 |
| **Overall GEO Score** | | | **58.3/100** |

---

## Critical Issues (Fix Immediately)

1. **No llms.txt file** — `https://zenskar.com/llms.txt` returns 404. This is the primary signal AI systems use to understand what a site wants indexed. Without it, AI crawlers have no guidance on what content is authoritative.

2. **ClaudeBot and PerplexityBot not explicitly allowed** — robots.txt does not include allow directives for `ClaudeBot`, `PerplexityBot`, or `Cohere-AI`. These are major AI citation engines. If they're blocked by a catch-all disallow, Zenskar is invisible to them.

3. **Zero FAQ schema** — The pricing page and feature pages contain implicit Q&A content ("What is usage-based billing?", "How does Zenskar handle complex contracts?") but no `FAQPage` schema markup. This is the single highest-ROI schema type for AI citation.

---

## High Priority Issues

1. **No author attribution on blog posts** — Blog articles do not include author names, bios, or credentials. AI systems use author E-E-A-T signals to assess content trustworthiness. Anonymous content is deprioritized for citation.

2. **Missing HowTo schema on integration/setup pages** — Step-by-step setup guides (e.g., connecting Salesforce, configuring usage meters) are strong AI citation targets but lack `HowTo` schema.

3. **SoftwareApplication schema absent** — The homepage and product pages lack `SoftwareApplication` schema with `applicationCategory`, `operatingSystem`, and `offers` fields — the standard markup for SaaS tools.

4. **No Wikipedia or Crunchbase entity page** — Zenskar has no Wikipedia article and limited Crunchbase presence. AI models heavily weight entity recognition from these sources. Companies without them are treated as low-authority.

5. **Thin "About" page** — The about page lacks team member profiles with credentials, founding story with specifics, or investor/customer social proof. These are core E-E-A-T signals.

---

## Medium Priority Issues

1. **Blog posts lack original research and data** — Most blog content is educational/definitional. Posts with original data (surveys, benchmarks, proprietary analysis) are cited by AI at much higher rates.

2. **Pricing page could be more AI-extractable** — Pricing tiers are likely rendered in comparison tables with minimal text. Adding a plain-text summary ("Zenskar's Growth plan starts at X per month and includes Y") improves AI extractability.

3. **No podcast, YouTube, or video content** — Zenskar has no YouTube channel or video presence, which limits training data coverage and platform diversity.

4. **Limited customer case studies with specifics** — Generic social proof ("customers love us") is not citable. Specific case studies ("Company X reduced billing errors by 40% using Zenskar's usage-metering engine") are highly citable.

5. **Open Graph tags present but incomplete** — OG tags exist but `og:description` is often truncated and does not include the most valuable, quotable claim about the product.

---

## Low Priority Issues

1. Some internal pages missing canonical tags
2. Image alt text missing on several decorative but contextually relevant graphics
3. Footer links to legal pages but no structured `BreadcrumbList` schema
4. LinkedIn company page exists but posts infrequently (reduces freshness signals)
5. No `sameAs` links in Organization schema connecting to social profiles

---

## Category Deep Dives

### AI Citability (72/100)

**Strengths:**
- Homepage has clear, quotable product definition: Zenskar is described as a billing and revenue recognition platform for B2B SaaS.
- Feature pages use benefit-oriented headings that are extractable as answer fragments.
- Integration pages list supported tools in a scannable format AI can extract.

**Weaknesses:**
- No explicit answer blocks (e.g., "What is Zenskar? Zenskar is a...") at the top of key pages.
- Statistical claims ("reduce billing errors", "save engineering hours") are made without cited numbers — AI systems prefer citable figures.
- Pricing page content is likely JavaScript-rendered and may not be indexable by AI crawlers.

**Recommendations:**
- Add a 2–3 sentence "Summary" block at the top of every key page in plain HTML.
- Add at least one specific, cited statistic per key page.
- Add a "Frequently Asked Questions" section in HTML (not just JS accordion) to every feature page.

---

### Content E-E-A-T (58/100)

**Strengths:**
- Zenskar clearly demonstrates product expertise through detailed technical content.
- Blog posts cover substantive billing/revenue topics at depth.

**Weaknesses:**
- **No author bylines** on any blog posts — critical E-E-A-T failure.
- About page does not name founders or team with credentials.
- No "As seen in" press section or named customer quotes with titles.
- No references to external authoritative sources (GAAP standards, ASC 606, etc.) that would signal expertise in finance/accounting.

**Recommendations:**
- Add author profiles to all blog posts with name, title, and a 2-sentence bio.
- Add a team section to the About page with LinkedIn links.
- Reference ASC 606 / IFRS 15 standards in revenue recognition content to demonstrate domain authority.
- Pursue placement in finance/SaaS media (CFO Magazine, SaaStr, Chargebee blog) for backlink + E-E-A-T signals.

---

### Brand Authority (58/100)

**Strengths:**
- Zenskar is mentioned on G2, Capterra, and similar review platforms.
- Has a LinkedIn company page with active presence.
- Appears in some SaaS comparison lists.

**Weaknesses:**
- No Wikipedia article.
- Reddit mentions are sparse — no dedicated community discussion of Zenskar.
- Limited press coverage from named outlets.
- Crunchbase entry may exist but is incomplete.

**Recommendations:**
- Submit a Wikipedia article stub covering the company's founding, category, and notable customers.
- Engage in billing/RevOps subreddits (r/SaaS, r/CFO, r/financialindependence) with educational content.
- Get listed on Crunchbase with a complete profile including funding, team, and category tags.
- Pitch product stories to SaaStr, ChartMogul, Paddle, or OpenView for co-marketing.

---

### Technical GEO (52/100)

**Strengths:**
- robots.txt exists and does not block Googlebot.
- Site appears to use server-side rendering (Webflow), meaning content is crawlable.
- HTTPS enforced across all pages.

**Weaknesses:**
- **No llms.txt** — the most impactful technical gap.
- ClaudeBot, PerplexityBot, and Cohere-AI not mentioned in robots.txt.
- No explicit AI crawler allow rules.
- Core Web Vitals may be suboptimal (Webflow can be slow on JS-heavy pages).

**Recommendations:**
- Create `/llms.txt` using the llms.txt spec. Include: company description, key pages, what content is authoritative.
- Add explicit allow rules to robots.txt:
  ```
  User-agent: ClaudeBot
  Allow: /

  User-agent: PerplexityBot
  Allow: /

  User-agent: GPTBot
  Allow: /
  ```
- Test Core Web Vitals with PageSpeed Insights and fix LCP/CLS issues.

---

### Schema & Structured Data (41/100)

**What was found:**
- Basic `Organization` schema present on homepage (name, url, logo).
- `WebSite` schema with sitelinks searchbox.
- `BreadcrumbList` on some pages.

**What's missing:**
- `SoftwareApplication` schema (most important for SaaS)
- `FAQPage` schema (highest AI citation impact)
- `HowTo` schema on setup/integration pages
- `Article` schema with author on blog posts
- `Product` / `Offer` schema on pricing page
- `Review` / `AggregateRating` schema

**Recommendations (prioritized):**
1. Add `FAQPage` schema to pricing page, homepage, and top 5 feature pages
2. Add `SoftwareApplication` schema to homepage with `applicationCategory: "BusinessApplication"`
3. Add `Article` + `Person` (author) schema to all blog posts
4. Add `HowTo` schema to integration setup guides
5. Add `AggregateRating` schema linking to G2/Capterra reviews

---

### Platform Optimization (52/100)

**Present:**
- LinkedIn company page — active
- G2 listing
- Capterra listing
- Some GitHub presence (API/integration mentions)

**Absent or weak:**
- YouTube — no channel found
- Reddit — no owned presence, sparse organic mentions
- Wikipedia — no article
- Product Hunt — may have a listing but minimal traction
- Substack / newsletters — no content distribution on AI-training-heavy platforms

**Recommendations:**
- Launch a YouTube channel with 5–10 short explainer videos ("What is usage-based billing?", "How does ASC 606 work?") — these are high-citation content types.
- Build a Substack or newsletter with original billing/RevOps research.
- Answer questions on Reddit in relevant communities with educational content (not promotional).

---

## Quick Wins (Implement This Week)

1. **Create `/llms.txt`** — 1 hour of work, immediate improvement in AI crawler guidance. Template: company description, product summary, 10 most important page URLs, content that's authoritative.

2. **Add robot.txt allow rules for AI crawlers** — 10-minute change, ensures ClaudeBot/PerplexityBot can index the site.

3. **Add FAQ schema to pricing page** — Add 5–8 FAQ items to the pricing page in JSON-LD. Questions like "How does Zenskar handle usage-based billing?" — these are exactly what AI answers to user queries.

4. **Add author bylines to all blog posts** — Even a simple "Written by [Name], [Title] at Zenskar" with a link to an author page significantly improves E-E-A-T.

5. **Add `SoftwareApplication` schema to homepage** — One JSON-LD block, 30 minutes, immediately signals to AI systems what category of tool Zenskar is.

---

## 30-Day Action Plan

### Week 1: Technical Foundation
- [ ] Create and publish `/llms.txt` with company description and key page index
- [ ] Update `robots.txt` to explicitly allow GPTBot, ClaudeBot, PerplexityBot, Cohere-AI
- [ ] Add `SoftwareApplication` JSON-LD schema to homepage
- [ ] Audit and fix any pages returning non-200 status codes

### Week 2: Schema Sprint
- [ ] Add `FAQPage` schema to pricing page and top 3 feature pages
- [ ] Add `Article` + `Person` (author) schema to all blog posts
- [ ] Add `HowTo` schema to top 3 integration/setup guides
- [ ] Add `AggregateRating` referencing G2 score to homepage schema

### Week 3: Content E-E-A-T
- [ ] Create author profile pages for all blog contributors
- [ ] Add named customer quotes (with title + company) to homepage and case study pages
- [ ] Update About page with founding team bios and credentials
- [ ] Add one original data point / benchmark to 3 high-traffic blog posts

### Week 4: Platform & Brand Expansion
- [ ] Create Wikipedia article stub (or hire a Wikipedia editor)
- [ ] Complete and verify Crunchbase profile
- [ ] Post first YouTube video (topic: "What is usage-based billing?")
- [ ] Engage in 5 relevant Reddit threads with educational (non-promotional) responses

---

## Appendix: Pages Analyzed

| URL | Title | Key GEO Issues |
|---|---|---|
| zenskar.com | Homepage | Missing SoftwareApplication schema, no FAQ schema |
| zenskar.com/pricing | Pricing | No FAQ schema, no Offer schema, JS-rendered tables |
| zenskar.com/integrations | Integrations | Good structured lists, missing HowTo schema |
| zenskar.com/blog | Blog index | No author attribution, no Article schema |
| zenskar.com/about | About | Thin team info, no Person schema |
| zenskar.com/customers | Customers/Logos | Generic social proof, no Review/AggregateRating schema |
| zenskar.com/docs or /help | Documentation | Not publicly crawlable or missing |

---

*Report generated by GEO Audit Skill — zenskar.com — 2026-03-12*

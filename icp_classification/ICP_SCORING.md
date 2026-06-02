# Zenskar ICP Scoring Reference

## What is the ICP?

Zenskar targets **B2B XaaS companies** (any X-as-a-Service model) that have a **custom, sales-led motion** and need billing automation. The goal is to identify companies where a senior finance/accounting persona exists and the pricing model is complex enough to justify Zenskar.

**Target ACV:** >$40,000 USD

---

## Hard Disqualifiers

If any of these match, the company is instantly **DISQUALIFIED** (all scores = 0):

| Category |
|---|
| Pure B2C (no B2B revenue) |
| Pure consulting / creative agency (hourly work only) |
| Bio pharma / Pharmaceutical |
| Private equity / Venture capital / Investment banking |
| Nonprofit / NGO |
| Government / Public sector |
| Pure physical goods / hardware / inventory (no services component) |
| Timesheet management software |

> **Exception:** Hardware + services (e.g. IoT) is **NOT** disqualified.

---

## Scoring Dimensions

Each dimension is scored **0–10**. The final score is a weighted average.

| Dimension | Weight |
|---|---|
| Company Size | 25% |
| Industry | 25% |
| Finance Persona | 20% |
| Geography | 15% |
| Pricing Complexity | 15% |

---

### 1. Company Size (25%)

Based on total employee count.

| Employees | Score | Label |
|---|---|---|
| 150 – 750 | **10** | Sweet spot |
| 750 – 1,500 | **8** | Upper target range |
| 1,500 – 2,000 | **5** | Above target range |
| 100 – 150 | **4** | Small, below target |
| 2,000 – 10,000 | **3** | Opportunistic |
| < 100 or > 10,000 | **1** | Outside range |

---

### 2. Industry (25%)

Based on whether the company is a B2B XaaS business.

| Industry Type | Score |
|---|---|
| **High-priority B2B XaaS:** SaaS, Cloud, API, DevTools/DevOps, AI/ML, Fintech, XaaS, IaaS, PaaS, HaaS, Cybersecurity, Software, IT Services, Managed Services, Data Services, Lending, Wealth Management, Recruiting/Staffing, Fleet Management, Logistics Services, Professional Consulting, Waste Management, IoT | **10** |
| Any other B2B service model (not physical goods/hardware) | **8** |
| **Exploratory B2B:** Telecom, Energy, Media, Travel, Automotive, Retail Tech, Real Estate Tech, Healthtech, Edtech, Financial Services | **6** |
| Other B2B | **4** |
| B2C-leaning | **1** |

---

### 3. Finance Persona (20%)

Signals that the company has senior finance or accounting leadership — the buyer persona for Zenskar.

**If enriched via email (Apollo data):**

| Signal | Score |
|---|---|
| CFO **and** Controller/VP Finance both listed | **10** |
| CFO or Chief Accounting Officer | **8** |
| VP/SVP/AVP of Finance or Accounting, Controller | **8** |
| Director/Head of Finance, Accounting, Revenue Accounting, or Billing | **7** |
| Finance Manager, Billing Manager, Revenue Manager, Accounting Manager | **5** |
| RevOps/BizOps/Business Systems leadership (VP/Director/Head) | **5** |
| COO, CTO, CPO, VP Product/Engineering (no finance title) | **4** |
| No finance people found, company has 500+ employees | **5** |
| No finance people found, company has < 500 employees | **3** |
| No data | **3** |

**If enriched via LinkedIn (contact's own title):**

| Signal | Score |
|---|---|
| Headline contains "Finance" + seniority word (Strategy, Operations, VP, Director, Head, CFO) | **8** |
| Headline contains "Finance" or "Accounting" without seniority signals | **5** |

**Strong Finance Titles (trigger score 7–10):**
CFO, Chief Financial Officer, SVP/AVP/VP of Finance, Vice President Finance, Director of Finance, Head of Finance, Financial Controller, Controller, Comptroller, Global Controller, Fractional CFO, CAO, Chief Accounting Officer, VP/Director/Head of Accounting, Head of Billing, Head of Order to Cash, Head of Revenue Accounting, Director of Revenue Accounting

**Moderate Finance Titles (trigger score 5):**
Finance Manager, Billing Manager, Revenue Manager, Accounting Manager, RevOps, BizOps, Revenue Operations, Business Operations, COO, CTO, CPO, VP/Head of Product or Engineering

---

### 4. Geography (15%)

Based on company HQ location.

| Location | Score |
|---|---|
| United States / Canada | **10** |
| United Kingdom | **8** |
| India or Israel — with 200+ employees in US/UK/Canada | **7** |
| India or Israel — without significant US/UK/Canada presence | **4** |
| Other | **2** |

---

### 5. Pricing Complexity (15%)

Signals that the company's billing model is complex enough to need Zenskar. Uses pricing page content if available, otherwise infers from description/keywords.

| Pricing Model | Score |
|---|---|
| Usage-based, metered, or consumption-based pricing | **10** |
| API/platform with metered billing | **9** |
| SaaS with enterprise tiers, contracts, or custom pricing | **7** |
| Marketplace or transaction-based model | **6** |
| Simple flat subscription only | **4** |
| Cannot determine | **5** *(neutral)* |

---

## Final Score & Verdict

| Score | Verdict |
|---|---|
| ≥ 7.5 | ✅ **Strong ICP Fit** |
| 5.5 – 7.4 | ⚠️ **Partial Fit** |
| 3.5 – 5.4 | 🔍 **Weak Fit** |
| < 3.5 or disqualified | ❌ **Not ICP** |

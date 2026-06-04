"""
ICP (Ideal Customer Profile) configuration for Zenskar.
Encodes all scoring rules from ICP.txt into structured data + LLM prompt.
Updated: March 2026
"""

# ── Hard Disqualifiers ──────────────────────────────────────────────
# If any of these match, the company is instantly NOT ICP (score = 0)
DISQUALIFIED_CATEGORIES = [
    "pure b2c",
    "pure consulting",
    "creative agency",
    "bio pharma",
    "pharmaceutical",
    "private equity",
    "venture capital",
    "investment banking",
    "nonprofit",
    "non-profit",
    "government",
    "public sector",
    "physical goods",
    "hardware only",
    "inventory management",
    "time sheet management",
    "timesheet management",
]

# ── Industry Classification ─────────────────────────────────────────
# B2B XaaS: X = Software, services, wealth, lending, logistics, data,
# recruiting, waste management, professional consulting, fleet management,
# IT services, etc.
# X != physical goods/hardware/inventory/timesheet (unless combined with
# services = IoT, which IS a good target)
HIGH_PRIORITY_INDUSTRIES = [
    "SaaS",
    "Cloud Infrastructure",
    "API",
    "DevTools",
    "DevOps",
    "AI",
    "Artificial Intelligence",
    "Machine Learning",
    "Fintech",
    "XaaS",
    "IaaS",
    "PaaS",
    "HaaS",
    "Cybersecurity",
    "Software",
    "Internet",
    "IT Services",
    "Managed Services",
    "Data Services",
    "Lending",
    "Wealth Management",
    "Recruiting",
    "Staffing",
    "Fleet Management",
    "Logistics Services",
    "Professional Services",
    "Waste Management Services",
    "IoT",
]

EXPLORATORY_INDUSTRIES = [
    "Telecom",
    "Communications",
    "Energy",
    "Utilities",
    "Media",
    "Advertising",
    "Entertainment",
    "Travel",
    "Transportation",
    "Automotive",
    "Mobility",
    "Retail Tech",
    "Real Estate Tech",
    "Healthtech",
    "Edtech",
    "Financial Services",
]

# ── Finance & Accounting Persona Titles ───────────────────────────────
STRONG_FINANCE_TITLES = [
    # Finance
    "CFO", "Chief Financial Officer",
    "SVP of Finance", "AVP of Finance", "VP Finance", "VP of Finance",
    "Vice President Finance", "Vice President of Finance",
    "Director of Finance", "Director Finance", "Director of Financial Operations",
    "Head of Finance", "Head of Financial Operations",
    "Head of Financial Transformation",
    "Financial Controller", "Controller", "Comptroller",
    "Global Controller", "VP Controller",
    "Fractional CFO",
    # Accounting
    "CAO", "Chief Accounting Officer",
    "SVP of Accounting", "AVP of Accounting", "VP Accounting", "VP of Accounting",
    "Director of Accounting", "Director Accounting",
    "Head of Accounting",
    # Revenue & Billing
    "Head of Billing", "Head of Order to Cash",
    "Head of Revenue Accounting", "Director of Revenue Accounting",
]

MODERATE_FINANCE_TITLES = [
    # Finance
    "Senior Finance Manager", "Finance Manager",
    "Financial Transformation Manager",
    "Senior Revenue Accounting Manager", "Revenue Accounting Manager",
    "Senior Billing Manager", "Billing Manager",
    "Revenue Manager",
    "Senior Manager Accounting", "Accounting Manager",
    "Lead Finance", "Senior Finance",
    # Business Systems / Rev-Ops
    "Head of Business Systems", "VP of Revenue Operations",
    "Head of Business Applications", "Director of Rev-Ops", "Director of Revenue Operations",
    "Head of Enterprise Systems", "Head of Rev-Ops", "Head of Revenue Operations",
    "Head of Business Technology", "Senior Rev-ops Manager", "Senior RevOps Manager",
    "Senior Manager Business Systems",
    "Senior Manager Business Applications",
    "Senior Manager of Enterprise Systems",
    "Revenue Systems",
    "RevOps", "Revenue Operations",
    "BizOps", "Business Operations",
    "Deal Desk",
    # Business Operations
    "COO", "Chief Operating Officer",
    "Director of Business Operations",
    "Head of Business Operations",
    "Business Operations Manager",
    # Product / Tech / Eng
    "CTO", "Chief Technology Officer",
    "CPO", "Chief Product Officer",
    "VP of Product", "VP of Engineering",
    "Head of Product", "Head of Engineering",
]

# ── Geography Priority ───────────────────────────────────────────────
TIER_1_COUNTRIES = ["United States", "US", "USA", "Canada", "CA"]
TIER_2_COUNTRIES = ["United Kingdom", "UK", "GB"]
# Cross-border: India/Israel qualify only if 200+ employees in US/UK/Canada
TIER_3_COUNTRIES = ["India", "IN", "Israel", "IL"]

# ── Employee Size Ranges ─────────────────────────────────────────────
# (min, max, score, label)
# Target range: 150-1500
EMPLOYEE_RANGES = [
    (150, 750, 10, "Sweet spot"),
    (750, 1500, 8, "Upper target range"),
    (1500, 2000, 5, "Above target range"),
    (100, 150, 4, "Small, below target"),
    (2000, 10000, 3, "Opportunistic"),
]

# ── Scoring Weights ──────────────────────────────────────────────────
DIMENSION_WEIGHTS = {
    "company_size": 0.25,
    "industry": 0.25,
    "geography": 0.15,
    "finance_persona": 0.20,
    "pricing_complexity": 0.15,
}

# ── Score Thresholds ─────────────────────────────────────────────────
THRESHOLD_STRONG = 7.5
THRESHOLD_PARTIAL = 5.5
THRESHOLD_WEAK = 3.5

# ── LLM System Prompt ───────────────────────────────────────────────
CLASSIFICATION_PROMPT = """You are an ICP (Ideal Customer Profile) classifier for Zenskar, a B2B billing and revenue recognition platform.

Given company data, you must score the company across 5 dimensions. Each score is 0-10.

## STEP 1: Check Hard Disqualifiers
If the company is ANY of these, set ALL scores to 0 and verdict to "DISQUALIFIED":
- Pure B2C company (no B2B revenue)
- Pure consulting or creative agency (hourly work only, no recurring software or managed services models)
- Bio pharma / Pharmaceutical
- Private equity / Venture capital / Investment banking
- Nonprofit organization
- Government / Public sector
- Pure physical goods / hardware / inventory company (NO services component)
  - EXCEPTION: Physical goods/hardware COMBINED with services (e.g., IoT) IS a valid target — do NOT disqualify

## STEP 2: Score Each Dimension (0-10)

### company_size (based on employee count)
- 150-750 employees → 10 (sweet spot)
- 750-1500 → 8 (upper target range)
- 1500-2000 → 5 (above target range)
- 100-150 → 4 (small, below target)
- 2000-10000 → 3 (opportunistic)
- <100 or >10000 → 1

### industry (B2B XaaS fit — any X-as-a-Service company with a custom sales-led motion)
- High-priority B2B XaaS: SaaS, Cloud, API, DevTools/DevOps, AI/ML, Fintech, XaaS, IaaS, PaaS, HaaS, Cybersecurity, Software, IT Services, Managed Services, Data Services, Lending, Wealth Management, Recruiting/Staffing, Fleet Management, Logistics Services, Professional Consulting Services, Waste Management Services, IoT → 10
- X = any B2B service model (not pure physical goods/hardware/inventory/timesheet management) → 8
- Exploratory B2B: Telecom, Energy, Media, Travel, Automotive, Retail tech, Real estate tech, Healthtech, Edtech, Financial Services → 6
- Other B2B → 4
- B2C-leaning → 1

### geography (HQ location)
- US / Canada → 10
- UK → 8
- India or Israel (cross-border, with 200+ employees in US/UK/Canada) → 7
- India or Israel (without significant US/UK/Canada presence) → 4
- Other → 2

### finance_persona (signals that company has senior finance/accounting leadership)
Score ONLY based on the data provided — specifically the "Finance/leadership people found" field.
Do NOT guess or use general knowledge about the company. Only score based on what's explicitly given.

The ICP requires at least 1 Senior Finance Title (CFO/Head/VP/Director of Finance) OR 1 Senior Accounting Title (CAO/Head/VP/Director of Accounting).

Scoring:
- "Finance/leadership people found" lists CFO AND Controller/VP Finance → 10
- Lists CFO or Chief Accounting Officer → 8
- Lists VP/SVP/AVP of Finance or Accounting, or Controller → 8
- Lists Director/Head of Finance, Accounting, Revenue Accounting, or Billing → 7
- Lists Finance Manager, Billing Manager, Revenue Manager, or Accounting Manager → 5
- Lists RevOps/BizOps/Business Systems leadership (VP/Director/Head) → 5
- Lists COO, CTO, CPO, VP Product/Engineering (but no finance title) → 4
- No "Finance/leadership people found" field but company has 500+ employees → 5 (likely has finance team but unconfirmed)
- No "Finance/leadership people found" field and company has <500 employees → 3 (unclear)
- No data at all → 3

If the input is a LinkedIn profile (no "Finance/leadership people found"), score based on the contact's own title/headline:
- Contact headline/title contains "Finance" AND ("Strategy" OR "Operations" OR "VP" OR "Director" OR "Head" OR "CFO") → 8 (senior finance person is the contact)
- Contact headline/title contains "Finance" or "Accounting" without seniority signals → 5

### pricing_complexity (signals the company has complex pricing that needs billing automation)
If "Pricing page content" is provided, use it as the primary signal. Otherwise infer from description/keywords.
- Usage-based, metered, or consumption-based pricing → 10
- API/platform with metered billing → 9
- SaaS with enterprise tiers, contracts, or custom pricing → 7
- Marketplace or transaction-based model → 6
- Simple flat subscription only → 4
- Cannot determine → 5 (neutral)

## OUTPUT FORMAT
You MUST respond with ONLY a JSON object (no markdown, no explanation outside JSON):
{
    "disqualified": false,
    "disqualification_reason": null,
    "scores": {
        "company_size": {"score": 8, "reasoning": "~300 employees, sweet spot range"},
        "industry": {"score": 10, "reasoning": "B2B SaaS platform"},
        "geography": {"score": 10, "reasoning": "HQ in San Francisco, US"},
        "finance_persona": {"score": 7, "reasoning": "Has Director of Finance and Head of Accounting"},
        "pricing_complexity": {"score": 9, "reasoning": "Usage-based API pricing with enterprise tiers"}
    },
    "overall_notes": "Strong ICP fit — B2B SaaS with complex usage-based pricing in target employee range."
}

If disqualified:
{
    "disqualified": true,
    "disqualification_reason": "Pure B2C company — consumer fashion brand",
    "scores": {
        "company_size": {"score": 0, "reasoning": "Disqualified"},
        "industry": {"score": 0, "reasoning": "Disqualified"},
        "geography": {"score": 0, "reasoning": "Disqualified"},
        "finance_persona": {"score": 0, "reasoning": "Disqualified"},
        "pricing_complexity": {"score": 0, "reasoning": "Disqualified"}
    },
    "overall_notes": "Not ICP — pure B2C company"
}
"""

"""
ICP Classifier — sends enriched company data to Groq LLM for scoring.
Uses GPT OSS 120B for nuanced reasoning about ICP fit.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv
from icp_config import (
    CLASSIFICATION_PROMPT,
    DIMENSION_WEIGHTS,
    THRESHOLD_STRONG,
    THRESHOLD_PARTIAL,
    THRESHOLD_WEAK,
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = "openai/gpt-oss-120b"


def _build_company_context(enriched_data: dict) -> str:
    """Build a concise company context string from enriched data for the LLM."""
    parts = []
    
    if enriched_data.get("company_name"):
        parts.append(f"Company: {enriched_data['company_name']}")
    if enriched_data.get("domain"):
        parts.append(f"Domain: {enriched_data['domain']}")
    if enriched_data.get("industry"):
        parts.append(f"Industry: {enriched_data['industry']}")
    if enriched_data.get("keywords"):
        kw = enriched_data["keywords"]
        if isinstance(kw, list):
            parts.append(f"Keywords: {', '.join(kw[:10])}")
    if enriched_data.get("description"):
        parts.append(f"Description: {enriched_data['description']}")
    if enriched_data.get("short_description"):
        parts.append(f"Short description: {enriched_data['short_description']}")
    if enriched_data.get("employee_count"):
        parts.append(f"Employees: {enriched_data['employee_count']}")
    if enriched_data.get("annual_revenue_printed"):
        parts.append(f"Revenue: {enriched_data['annual_revenue_printed']}")
    if enriched_data.get("location"):
        parts.append(f"Location: {enriched_data['location']}")
    if enriched_data.get("country"):
        parts.append(f"Country: {enriched_data['country']}")
    if enriched_data.get("founded_year"):
        parts.append(f"Founded: {enriched_data['founded_year']}")
    if enriched_data.get("technologies"):
        techs = enriched_data["technologies"]
        if isinstance(techs, list):
            parts.append(f"Tech stack: {', '.join(str(t) for t in techs[:8])}")
    if enriched_data.get("funding_total"):
        parts.append(f"Total funding: {enriched_data['funding_total']}")
    if enriched_data.get("latest_funding_round"):
        parts.append(f"Latest round: {enriched_data['latest_funding_round']}")
    if enriched_data.get("specialities"):
        specs = enriched_data["specialities"]
        if isinstance(specs, list):
            parts.append(f"Specialities: {', '.join(str(s) for s in specs[:8])}")
    if enriched_data.get("website_url"):
        parts.append(f"Website: {enriched_data['website_url']}")

    # Person-specific fields (from LinkedIn enrichment)
    if enriched_data.get("person_name"):
        parts.append(f"Contact person: {enriched_data['person_name']}")
    if enriched_data.get("person_title"):
        parts.append(f"Contact title: {enriched_data['person_title']}")
    if enriched_data.get("person_headline"):
        parts.append(f"Contact headline: {enriched_data['person_headline']}")

    # Finance personas found at the company (from Apollo people search)
    if enriched_data.get("finance_people"):
        people_strs = [f"{p['name']} ({p['title']})" for p in enriched_data["finance_people"]]
        parts.append(f"Finance/leadership people found: {'; '.join(people_strs)}")

    if enriched_data.get("pricing_page_content"):
        parts.append(f"Pricing page content: {enriched_data['pricing_page_content'][:1500]}")

    return "\n".join(parts) if parts else "Minimal data available."


def classify_company(enriched_data: dict) -> dict:
    """
    Classify a company against Zenskar's ICP using Groq LLM.

    Args:
        enriched_data: Normalized company data from enrichment layer.

    Returns:
        Classification result dict with scores, verdict, and reasoning.
    """
    # If enrichment failed completely, return error
    if enriched_data.get("error") and not enriched_data.get("company_name"):
        return {
            "success": False,
            "error": enriched_data["error"],
            "input": enriched_data.get("email") or enriched_data.get("linkedin_url", "unknown"),
        }

    company_context = _build_company_context(enriched_data)

    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Classify this company:\n\n{company_context}"},
            ],
            temperature=0.1,  # Low temperature for consistent scoring
            max_tokens=2048,
        )

        raw_response = response.choices[0].message.content.strip()
        
        # Parse JSON from response (handle potential markdown code blocks)
        json_str = raw_response
        if "```" in json_str:
            # Extract JSON from code block
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            json_str = json_str.strip()

        scores_data = json.loads(json_str)
        return _build_result(enriched_data, scores_data)

    except json.JSONDecodeError as e:
        print(f"[classifier] JSON parse error: {e}")
        print(f"[classifier] Raw response: {raw_response}")
        return {
            "success": False,
            "error": f"LLM returned invalid JSON: {str(e)}",
            "input": enriched_data.get("email") or enriched_data.get("linkedin_url", "unknown"),
            "raw_response": raw_response,
        }
    except Exception as e:
        print(f"[classifier] Groq API error: {e}")
        return {
            "success": False,
            "error": f"Classification failed: {str(e)}",
            "input": enriched_data.get("email") or enriched_data.get("linkedin_url", "unknown"),
        }


def _build_result(enriched_data: dict, scores_data: dict) -> dict:
    """Build the final classification result from LLM scores."""
    
    # Handle disqualification
    if scores_data.get("disqualified"):
        return {
            "success": True,
            "input": enriched_data.get("email") or enriched_data.get("linkedin_url", "unknown"),
            "company_name": enriched_data.get("company_name", "Unknown"),
            "disqualified": True,
            "disqualification_reason": scores_data.get("disqualification_reason", "Disqualified"),
            "verdict": "NOT ICP",
            "verdict_emoji": "❌",
            "weighted_score": 0,
            "scores": scores_data.get("scores", {}),
            "overall_notes": scores_data.get("overall_notes", ""),
            "enriched_data": enriched_data,
        }

    # Calculate weighted score
    scores = scores_data.get("scores", {})
    weighted_score = 0
    for dimension, weight in DIMENSION_WEIGHTS.items():
        dim_data = scores.get(dimension, {})
        dim_score = dim_data.get("score", 5)  # Default to neutral
        weighted_score += dim_score * weight

    weighted_score = round(weighted_score, 1)

    # Determine verdict
    if weighted_score >= THRESHOLD_STRONG:
        verdict = "STRONG ICP FIT"
        emoji = "✅"
    elif weighted_score >= THRESHOLD_PARTIAL:
        verdict = "PARTIAL FIT"
        emoji = "⚠️"
    elif weighted_score >= THRESHOLD_WEAK:
        verdict = "WEAK FIT"
        emoji = "🟡"
    else:
        verdict = "NOT ICP"
        emoji = "❌"

    return {
        "success": True,
        "input": enriched_data.get("email") or enriched_data.get("linkedin_url", "unknown"),
        "company_name": enriched_data.get("company_name", "Unknown"),
        "disqualified": False,
        "verdict": verdict,
        "verdict_emoji": emoji,
        "weighted_score": weighted_score,
        "scores": scores,
        "overall_notes": scores_data.get("overall_notes", ""),
        "enriched_data": enriched_data,
    }


def format_result_text(result: dict) -> str:
    """Format a classification result as a human-readable text block."""
    if not result.get("success"):
        return f"❗ Error for `{result.get('input', 'unknown')}`: {result.get('error', 'Unknown error')}"

    company = result.get("company_name", "Unknown")

    if result.get("disqualified"):
        return (
            f"❌ *NOT ICP — {company}*\n"
            f"Reason: {result.get('disqualification_reason', 'Disqualified')}\n"
            f"_{result.get('overall_notes', '')}_"
        )

    lines = [
        f"{result['verdict_emoji']} *{result['verdict']} — {company}*",
        f"",
        f"*Score: {result['weighted_score']}/10*",
        f"",
        f"📊 *Breakdown:*",
    ]

    dimension_emojis = {
        "company_size": "🏢",
        "industry": "🏭",
        "geography": "🌍",
        "finance_persona": "👔",
        "pricing_complexity": "💰",
    }

    dimension_labels = {
        "company_size": "Company Size",
        "industry": "Industry",
        "geography": "Geography",
        "finance_persona": "Finance Persona",
        "pricing_complexity": "Pricing",
    }

    scores = result.get("scores", {})
    for dim_key in DIMENSION_WEIGHTS:
        dim = scores.get(dim_key, {})
        score = dim.get("score", "?")
        reasoning = dim.get("reasoning", "")
        emoji = dimension_emojis.get(dim_key, "📌")
        label = dimension_labels.get(dim_key, dim_key)
        lines.append(f"  {emoji} {label}: *{score}/10* — {reasoning}")

    if result.get("overall_notes"):
        lines.append(f"")
        lines.append(f"💡 _{result['overall_notes']}_")

    # Add source info
    enriched = result.get("enriched_data", {})
    source_parts = []
    if enriched.get("employee_count"):
        source_parts.append(f"{enriched['employee_count']} employees")
    if enriched.get("location") and enriched["location"] != "Unknown":
        source_parts.append(enriched["location"])
    if enriched.get("domain"):
        source_parts.append(enriched["domain"])
    if source_parts:
        lines.append(f"")
        lines.append(f"_Source: {' · '.join(source_parts)}_")

    return "\n".join(lines)


def format_bulk_summary(results: list[dict]) -> str:
    """Format multiple results as a summary table for Slack."""
    if not results:
        return "No results to display."

    lines = ["*📋 ICP Classification Results*", ""]

    # Summary counts
    verdicts = {}
    for r in results:
        v = r.get("verdict", "ERROR") if r.get("success") else "ERROR"
        verdicts[v] = verdicts.get(v, 0) + 1

    summary_parts = []
    for verdict, count in sorted(verdicts.items()):
        emoji_map = {
            "STRONG ICP FIT": "✅", "PARTIAL FIT": "⚠️",
            "WEAK FIT": "🟡", "NOT ICP": "❌", "ERROR": "❗"
        }
        summary_parts.append(f"{emoji_map.get(verdict, '📌')} {verdict}: {count}")
    lines.append(" | ".join(summary_parts))
    lines.append("")

    # Individual results (compact)
    for r in results:
        if not r.get("success"):
            lines.append(f"❗ `{r.get('input', '?')}` — {r.get('error', 'Error')}")
        elif r.get("disqualified"):
            lines.append(f"❌ *{r.get('company_name', '?')}* — {r.get('disqualification_reason', 'Not ICP')}")
        else:
            lines.append(
                f"{r['verdict_emoji']} *{r.get('company_name', '?')}* — "
                f"{r['weighted_score']}/10 ({r['verdict']})"
            )

    return "\n".join(lines)

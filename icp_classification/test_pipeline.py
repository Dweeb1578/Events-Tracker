"""Quick test script to verify the pipeline works."""
import sys
import os
import json

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from enrichment import enrich_profile
from classifier import classify_company, format_result_text

# Test 1: Known B2B SaaS company (should be ICP)
print("=" * 60)
print("TEST 1: test@stripe.com (should be strong/partial fit)")
print("=" * 60)
enriched = enrich_profile("test@stripe.com")
print(f"Company: {enriched.get('company_name', 'N/A')}")
print(f"Industry: {enriched.get('industry', 'N/A')}")
print(f"Employees: {enriched.get('employee_count', 'N/A')}")
print(f"Location: {enriched.get('location', 'N/A')}")
print(f"Source: {enriched.get('source', 'N/A')}")
print()

result = classify_company(enriched)
print(f"Success: {result.get('success')}")
print(f"Verdict: {result.get('verdict', 'N/A')}")
print(f"Score: {result.get('weighted_score', 'N/A')}/10")
print(f"Disqualified: {result.get('disqualified', 'N/A')}")
scores = result.get("scores", {})
for dim, data in scores.items():
    print(f"  {dim}: {data.get('score', '?')}/10 - {data.get('reasoning', '')}")
print(f"Notes: {result.get('overall_notes', '')}")
print()

# Test 2: Gmail (free email, should error)
print("=" * 60)
print("TEST 2: john@gmail.com (free email, should show error)")
print("=" * 60)
enriched2 = enrich_profile("john@gmail.com")
print(f"Error: {enriched2.get('error', 'N/A')}")
print()

# Test 3: Format check
print("=" * 60)
print("TEST 3: Formatted output")
print("=" * 60)
print(format_result_text(result))

"""Capture test output to a file for viewing."""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()
from enrichment import enrich_profile
from classifier import classify_company, format_result_text

output_lines = []

def log(msg=""):
    output_lines.append(msg)

# Test 1
log("=" * 60)
log("TEST 1: test@stripe.com")
log("=" * 60)
enriched = enrich_profile("test@stripe.com")
log(f"Company: {enriched.get('company_name', 'N/A')}")
log(f"Industry: {enriched.get('industry', 'N/A')}")
log(f"Employees: {enriched.get('employee_count', 'N/A')}")
log(f"Location: {enriched.get('location', 'N/A')}")
log(f"Country: {enriched.get('country', 'N/A')}")
log()

result = classify_company(enriched)
log(f"Verdict: {result.get('verdict', 'N/A')}")
log(f"Score: {result.get('weighted_score', 'N/A')}/10")
log(f"Disqualified: {result.get('disqualified', 'N/A')}")
log()
log("Scores:")
for dim, data in result.get("scores", {}).items():
    log(f"  {dim}: {data.get('score', '?')}/10 - {data.get('reasoning', '')}")
log()
log(f"Notes: {result.get('overall_notes', '')}")
log()
log("Formatted output:")
log("-" * 60)
log(format_result_text(result))
log("-" * 60)

# Test 2: Free email
log()
log("=" * 60)
log("TEST 2: john@gmail.com (free email)")
log("=" * 60)
enriched2 = enrich_profile("john@gmail.com")
result2 = classify_company(enriched2)
log(format_result_text(result2))

# Write to file
with open("test_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Output saved to test_output.txt")

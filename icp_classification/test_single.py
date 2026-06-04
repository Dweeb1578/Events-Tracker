"""Quick test: https://www.linkedin.com/in/rohitpathak"""
import sys, os
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()
from enrichment import enrich_profile
from classifier import classify_company, format_result_text

url = "https://www.linkedin.com/in/slaterlatour"
print(f"Testing URL: {url}")
enriched = enrich_profile(url)
output = []
output.append("=== Enriched Data ===")
for k, v in enriched.items():
    if k != "raw_data" and v:
        output.append(f"  {k}: {v}")

output.append("")
result = classify_company(enriched)
output.append("=== Classification ===")
output.append(format_result_text(result))

with open("test_output.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))
print("Done - saved to test_output.txt")

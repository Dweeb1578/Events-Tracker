import os
import httpx
from dotenv import load_dotenv

load_dotenv()
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

try:
    print("Testing /search endpoint with linkedin URL...")
    res = httpx.post(
        "https://api.apollo.io/v1/organizations/search",
        json={"q_organization_linkedin_url": "https://www.linkedin.com/company/rain-app-inc-/"},
        headers={"X-Api-Key": APOLLO_API_KEY},
        timeout=10
    )
    res.raise_for_status()
    data = res.json()
    orgs = data.get("organizations", [])
    if orgs:
        print(f"Found via Search: {orgs[0].get('primary_domain')}, {orgs[0].get('estimated_num_employees')} employees")
    else:
        print("No valid orgs in Search.")
except Exception as e:
    print(f"Search error: {e}")

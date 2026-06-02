import os
import httpx
from dotenv import load_dotenv
import json

load_dotenv()
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")

domain = "meter.com"

print("Testing /search endpoint with q_organization_domains string...")
try:
    res = httpx.post(
        "https://api.apollo.io/v1/organizations/search",
        json={"q_organization_domains": domain},
        headers={"X-Api-Key": APOLLO_API_KEY},
        timeout=10
    )
    print(res.status_code)
    data = res.json()
    orgs = data.get("organizations", [])
    if orgs:
        print(f"Found via string: {orgs[0].get('primary_domain')}, {orgs[0].get('estimated_num_employees')} employees")
    else:
        print("No valid orgs in Search via string.")
except Exception as e:
    print(f"Search error: {e}")

print("\nTesting /search endpoint with q_organization_domains list...")
try:
    res = httpx.post(
        "https://api.apollo.io/v1/organizations/search",
        json={"q_organization_domains": [domain]},
        headers={"X-Api-Key": APOLLO_API_KEY},
        timeout=10
    )
    print(res.status_code)
    data = res.json()
    orgs = data.get("organizations", [])
    if orgs:
        print(f"Found via list: {orgs[0].get('primary_domain')}, {orgs[0].get('estimated_num_employees')} employees")
    else:
        print("No valid orgs in Search via list.")
except Exception as e:
    print(f"Search error: {e}")

print("\nTesting /search endpoint with q_organization_domains containing newlines (strip it)...")
try:
    res = httpx.post(
        "https://api.apollo.io/v1/organizations/search",
        json={"q_organization_domains": domain.strip() + "\n"},
        headers={"X-Api-Key": APOLLO_API_KEY},
        timeout=10
    )
    data = res.json()
    orgs = data.get("organizations", [])
    if orgs:
        print("Found with newline!")
    else:
        print("Not found with newline")
except Exception as e:
    print("error")

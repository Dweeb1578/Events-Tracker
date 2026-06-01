"""Pytest path setup: make repo root and the copied icp_classification package importable."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICP = os.path.join(ROOT, "icp_classification")

for p in (ROOT, ICP):
    if p not in sys.path:
        sys.path.insert(0, p)

"""Parse event date + city from a LinkedIn post's text. Best-effort, returns '' on miss."""
import re
from datetime import datetime

_CITY_PATTERNS = [
    ("NYC", ["nyc", "new york city", "new york", "manhattan", "brooklyn"]),
    ("SF", ["san francisco", "bay area", " sf ", "soma", "silicon valley"]),
]

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}


def parse_event_city(text: str) -> str:
    """Return 'NYC', 'SF', or '' based on substring signals (pads spaces to catch ' sf ')."""
    if not text:
        return ""
    t = f" {text.lower()} "
    for label, needles in _CITY_PATTERNS:
        if any(n in t for n in needles):
            return label
    return ""


def parse_event_date(text: str) -> str:
    """Return an ISO date 'YYYY-MM-DD' if a clear date is present, else ''."""
    if not text:
        return ""
    iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    # "July 15, 2026" / "July 15 2026"
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(20\d{2})\b", text)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return datetime(int(m.group(3)), _MONTHS[m.group(1).lower()],
                            int(m.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            return ""
    return ""

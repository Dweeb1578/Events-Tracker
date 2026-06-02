"""Derive engagement strength + a human 'warm reason' for outreach."""


def engagement_strength(engagement_type: str) -> str:
    """Binary intent signal (single actor can't give reaction sub-types)."""
    return "high (comment)" if engagement_type == "commenter" else "medium (reaction)"


def warm_reason(engager: dict) -> str:
    """One-line personalized hook for whoever sends the invite."""
    verb = "Commented on" if engager.get("engagement_type") == "commenter" else "Reacted to"
    company = engager.get("source_post_company", "") or "a competitor"
    preview = (engager.get("source_post_preview", "") or "").strip().rstrip(".")
    topic = f" about a {preview}" if preview else ""
    city = engager.get("event_city", "")
    suffix = f" ({city})" if city else ""
    return f"{verb} {company}'s post{topic}{suffix}"

"""Derive engagement strength + a human 'warm reason' for outreach."""


def engagement_strength(engagement_type: str) -> str:
    """Binary intent signal (single actor can't give reaction sub-types)."""
    return "high (comment)" if engagement_type == "commenter" else "medium (reaction)"


_PREVIEW_MAX = 60


def _clean_preview(preview: str) -> str:
    """Collapse newlines/whitespace runs and truncate so the hook stays one line."""
    collapsed = " ".join(preview.split()).rstrip(".")
    if len(collapsed) > _PREVIEW_MAX:
        collapsed = collapsed[:_PREVIEW_MAX].rstrip() + "…"
    return collapsed


def warm_reason(engager: dict) -> str:
    """One-line personalized hook for whoever sends the invite."""
    verb = "Commented on" if engager.get("engagement_type") == "commenter" else "Reacted to"
    company = engager.get("source_post_company", "") or "a competitor"
    preview = _clean_preview(engager.get("source_post_preview", "") or "")
    topic = f" about a {preview}" if preview else ""
    city = engager.get("event_city", "")
    suffix = f" ({city})" if city else ""
    return f"{verb} {company}'s post{topic}{suffix}"

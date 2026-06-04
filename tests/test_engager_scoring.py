from agents.engager_scoring import engagement_strength, warm_reason


def test_engagement_strength():
    assert engagement_strength("commenter") == "high (comment)"
    assert engagement_strength("liker") == "medium (reaction)"
    assert engagement_strength("") == "medium (reaction)"


def test_warm_reason_comment_with_city():
    e = {"engagement_type": "commenter", "source_post_company": "Orb",
         "event_city": "NYC", "source_post_preview": "CFO dinner in NYC"}
    assert warm_reason(e) == "Commented on Orb's post about a CFO dinner in NYC (NYC)"


def test_warm_reason_like_without_city():
    e = {"engagement_type": "liker", "source_post_company": "Operators Guild",
         "event_city": "", "source_post_preview": "Finance leaders roundtable"}
    assert warm_reason(e) == "Reacted to Operators Guild's post about a Finance leaders roundtable"


def test_warm_reason_collapses_newlines_and_truncates():
    e = {"engagement_type": "liker", "source_post_company": "Finance Alliance",
         "event_city": "",
         "source_post_preview": "🚨Speaker applications are now open for CFO Summit London 2026 🚨\n\nI'm looking for CFOs"}
    reason = warm_reason(e)
    # one line, no embedded newlines
    assert "\n" not in reason
    # truncated with ellipsis, stays bounded
    assert reason.endswith("…")
    assert len(reason) < 110

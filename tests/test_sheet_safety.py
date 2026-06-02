from agents.sheet_safety import escape_formula


def test_escapes_leading_formula_chars():
    for bad in ("=1+1", "+1", "-1", "@x", '=HYPERLINK("http://evil")'):
        out = escape_formula(bad)
        assert out.startswith("'") and out[1:] == bad


def test_leaves_safe_strings_untouched():
    for ok in ("Jane Doe", "VP Finance", "https://linkedin.com/in/x", "NYC", ""):
        assert escape_formula(ok) == ok


def test_passes_non_strings_through():
    assert escape_formula(86) == 86
    assert escape_formula(None) is None

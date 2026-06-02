"""Neutralize spreadsheet formula injection in untrusted text cells."""

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_formula(value):
    """Prefix an apostrophe to strings that begin with a formula trigger char.
    Non-strings pass through unchanged so numeric cells stay numeric."""
    if isinstance(value, str) and value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value

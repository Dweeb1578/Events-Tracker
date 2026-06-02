"""Neutralize spreadsheet formula injection in untrusted text cells."""

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def escape_formula(value):
    """Prefix an apostrophe to strings whose first non-whitespace char is a formula
    trigger (=, +, -, @). Leading whitespace/control chars are ignored when deciding,
    so '\\t=cmd' and ' =1+1' are also neutralized. Non-strings pass through unchanged."""
    if isinstance(value, str) and value.lstrip()[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value

"""Keyword/location filtering for US-based remote virtual-assistant roles."""
import re

VA_KEYWORDS = [
    "virtual assistant", "virtual admin", "executive assistant",
    "administrative assistant", "personal assistant", "remote assistant",
    "admin assistant", "ea ", " va ", "office assistant",
]

US_HINTS = [
    "united states", "usa", "u.s.", "us only", "us-based", "us based",
    "north america", "americas", "est", "pst", "cst", "mst",
    # common state abbreviations show up in locations
    " ny", " ca", " tx", " fl", "remote - us", "remote (us",
]

# Reject listings that are clearly restricted to other regions.
NON_US_BLOCK = [
    "europe only", "emea only", "uk only", "india only", "philippines only",
    "latam only", "apac only", "eu only", "canada only", "australia only",
]


def _norm(text: str | None) -> str:
    return (text or "").lower()


def is_virtual_assistant(title: str, description: str = "") -> bool:
    hay = _norm(title) + " " + _norm(description)
    return any(k in hay for k in VA_KEYWORDS)


def is_us_based(location: str, description: str = "") -> bool:
    loc = _norm(location)
    desc = _norm(description)
    blob = loc + " " + desc

    if any(b in blob for b in NON_US_BLOCK):
        return False

    # "remote" with a US hint, or an explicit US hint anywhere
    if any(h in blob for h in US_HINTS):
        return True

    # Many remote boards say "Anywhere" / "Worldwide" — treat as eligible
    # since a US applicant can apply, but flag-neutral.
    if re.search(r"\b(anywhere|worldwide|global|remote)\b", blob):
        return True

    return False


def matches(title: str, location: str, description: str = "") -> bool:
    return is_virtual_assistant(title, description) and is_us_based(location, description)


def match_score(title: str, location: str, description: str = "") -> int:
    """Rough 0-100 confidence that this is a US remote VA role."""
    score = 0
    hay = _norm(title) + " " + _norm(description)
    if "virtual assistant" in hay:
        score += 50
    elif is_virtual_assistant(title, description):
        score += 30
    loc = _norm(location) + " " + _norm(description)
    if any(h in loc for h in ("united states", "usa", "us-based", "us based", "us only")):
        score += 40
    elif any(h in loc for h in US_HINTS):
        score += 20
    if "remote" in loc:
        score += 10
    return min(score, 100)

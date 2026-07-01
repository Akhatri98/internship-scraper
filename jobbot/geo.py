"""Best-effort country inference from ATS location data.

ATS boards report location every which way: some give a structured country
(name or ISO code — smartrecruiters/workable/breezy/recruitee/ashby), others
only a free-text string ("London, UK", "Remote - US", "San Francisco, CA" —
greenhouse/lever). We normalise to a display country name where we can and return
None when we honestly can't. `country` is a filter aid (esp. US-vs-international
for work-authorization), not a guarantee — treat missing as "unknown", not "US".
"""
import re

# ISO-3166 alpha-2 (and a couple alpha-3 / colloquial) -> display name.
_ISO2 = {
    "us": "United States", "usa": "United States",
    "gb": "United Kingdom", "uk": "United Kingdom",
    "ca": "Canada", "au": "Australia", "nz": "New Zealand",
    "de": "Germany", "fr": "France", "es": "Spain", "it": "Italy",
    "ie": "Ireland", "nl": "Netherlands", "be": "Belgium", "ch": "Switzerland",
    "at": "Austria", "se": "Sweden", "no": "Norway", "dk": "Denmark",
    "fi": "Finland", "pl": "Poland", "pt": "Portugal", "cz": "Czechia",
    "ro": "Romania", "gr": "Greece", "hu": "Hungary",
    "in": "India", "sg": "Singapore", "jp": "Japan", "kr": "South Korea",
    "cn": "China", "hk": "Hong Kong", "tw": "Taiwan", "my": "Malaysia",
    "ph": "Philippines", "id": "Indonesia", "th": "Thailand", "vn": "Vietnam",
    "il": "Israel", "ae": "United Arab Emirates", "sa": "Saudi Arabia",
    "za": "South Africa", "ng": "Nigeria", "ke": "Kenya", "eg": "Egypt",
    "br": "Brazil", "mx": "Mexico", "ar": "Argentina", "cl": "Chile",
    "co": "Colombia",
    "lv": "Latvia", "lt": "Lithuania", "ee": "Estonia", "hr": "Croatia",
    "si": "Slovenia", "sk": "Slovakia", "rs": "Serbia", "tr": "Turkey",
    "ua": "Ukraine", "bg": "Bulgaria",
}

# Colloquial / alternate spellings + localized (native-language) names -> display
# name. ATSs on non-English boards report the country in its own language, which
# otherwise slips through as a duplicate (e.g. "Nederland" vs "Netherlands").
_ALIASES = {
    "united states of america": "United States", "america": "United States",
    "u.s.": "United States", "u.s.a.": "United States", "us of a": "United States",
    "great britain": "United Kingdom", "britain": "United Kingdom",
    "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "u.k.": "United Kingdom",
    "uae": "United Arab Emirates", "korea": "South Korea",
    "czech republic": "Czechia", "cesko": "Czechia", "česko": "Czechia",
    # localized country names seen in ATS feeds
    "nederland": "Netherlands", "the netherlands": "Netherlands",
    "deutschland": "Germany", "allemagne": "Germany", "duitsland": "Germany",
    "frankrijk": "France", "frankreich": "France", "francia": "France",
    "brasil": "Brazil",
    "italia": "Italy", "italie": "Italy", "italien": "Italy",
    "belgique": "Belgium", "belgië": "Belgium", "belgie": "Belgium", "belgien": "Belgium",
    "schweiz": "Switzerland", "suisse": "Switzerland", "svizzera": "Switzerland",
    "españa": "Spain", "espana": "Spain", "espagne": "Spain", "spanien": "Spain",
    "österreich": "Austria", "osterreich": "Austria", "autriche": "Austria",
    "danmark": "Denmark", "sverige": "Sweden", "norge": "Norway", "suomi": "Finland",
    "polska": "Poland", "singapour": "Singapore",
    "latvija": "Latvia", "lietuva": "Lithuania", "eesti": "Estonia",
    "hrvatska": "Croatia", "slovensko": "Slovakia", "slovenija": "Slovenia",
    "srbija": "Serbia", "türkiye": "Turkey", "turkiye": "Turkey",
    "magyarország": "Hungary", "magyarorszag": "Hungary", "éire": "Ireland",
}

# US state / territory postal codes -> "City, ST" strings imply United States.
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}

# Canonical display names we recognise when they appear verbatim in free text.
_KNOWN_LOWER = {name.lower(): name for name in set(_ISO2.values()) | set(_ALIASES.values())}

# Structured values that are NOT countries (some ATSs stuff these in the field).
_NON_COUNTRY = {"remote", "null", "none", "n/a", "na", "various", "multiple",
                "global", "worldwide", "anywhere", "hybrid", "onsite", "on-site",
                "any location", "any", "flexible", "multiple locations", "other"}

_SPLIT = re.compile(r"[,/|;–—]|\s-\s")
_NAME_OK = re.compile(r"[A-Za-z .'&-]+")


def _canon(token) -> str | None:
    """Map one token (code, alias, or known full name) to a display country."""
    if not token:
        return None
    t = str(token).strip().lower().strip(".")
    if not t or t in _NON_COUNTRY:
        return None
    return _ISO2.get(t) or _ALIASES.get(t) or _KNOWN_LOWER.get(t)


def country_of(structured=None, location=None) -> str | None:
    """Best-effort country. `structured` (an ATS-provided country name/ISO code)
    is authoritative; otherwise parse the free-text `location` string."""
    c = _canon(structured)
    if c:
        return c
    # A structured value we don't have in our tables but which looks like a real
    # country name — trust the ATS field rather than drop it (keeps long-tail
    # countries like "Philippines" even if unlisted).
    if structured:
        s = str(structured).strip()
        if len(s) > 3 and s.lower() not in _NON_COUNTRY and _NAME_OK.fullmatch(s):
            return s if s.istitle() else s.title()

    if not location:
        return None
    segs = [s.strip() for s in _SPLIT.split(location) if s.strip()]
    # "City, ST" — a 2-letter US state code inside a multi-part string means US.
    # (Guarded to multi-part so a lone ambiguous "CA"/"IN" isn't force-read as US.)
    if len(segs) >= 2 and any(s.upper() in _US_STATES for s in segs):
        return "United States"
    # Otherwise the country is usually the right-most segment ("Berlin, Germany").
    for seg in reversed(segs):
        c = _canon(seg)
        if c:
            return c
    return None

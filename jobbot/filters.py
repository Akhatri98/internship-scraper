"""Student-role keyword filter (applied by Refresh, Component B).

A job passes only if BOTH gates hit:
  HARD   : a student-role term (intern / co-op / new-grad / early-career) in the
           TITLE, OR a structured employment-type signal from the ATS
           (Lever commitment, Ashby employmentType).
  OR-BAG : at least one tech term (software / AI / ML / data / engineering /
           developer) anywhere in title OR description.

CRITICAL: the HARD gate reads the TITLE only, never the description. Full-time
senior roles routinely mention "interns"/"co-op"/"early career" in description
boilerplate (mentoring blurbs, benefits/EEO sections) — matching that turned
~every job at Stripe/OpenAI into a false "intern". Real student roles say so in
the title or are tagged by the ATS. The tech OR-bag is only a relevance signal,
so it may scan the description.

All matching is word-boundary regex so "intern" does NOT fire on "internal" /
"international", and "co-op" does NOT fire on "cooperative". Returns the union of
matched labels for listings.keywords_matched.
"""
import re

# (label, compiled pattern)
HARD_PATTERNS = [
    ("intern", re.compile(r"\bintern(ship)?s?\b", re.I)),
    ("co-op", re.compile(r"\bco[\s-]?ops?\b", re.I)),
    ("new grad", re.compile(r"\bnew[\s-]?grad(uate)?s?\b", re.I)),
    ("early career", re.compile(r"\bearly[\s-]?career\b", re.I)),
]

ORBAG_PATTERNS = [
    ("software", re.compile(r"\bsoftware\b", re.I)),
    ("AI", re.compile(r"\b(ai|artificial intelligence)\b", re.I)),
    ("ML", re.compile(r"\b(ml|machine learning)\b", re.I)),
    ("data", re.compile(r"\bdata\b", re.I)),
    ("engineering", re.compile(r"\bengineer(ing|s)?\b", re.I)),
    ("developer", re.compile(r"\bdevelop(er|ment)?\b", re.I)),
]

# Matches the ATS employment-type controlled vocab ("Intern", "Internship").
# Prefix match (no trailing \b) so "Internship" is caught; the field is a
# controlled vocabulary so there's no "internal"-style false positive risk here.
_INTERN_TYPE = re.compile(r"\bintern", re.I)


def _match(text: str, patterns) -> list[str]:
    return [label for label, pat in patterns if pat.search(text)]


def evaluate(title: str, description: str = "", employment_type: str = "") -> tuple[bool, list[str]]:
    """Return (passes, matched_labels)."""
    title = title or ""

    # HARD gate: TITLE only (+ structured employment type). Never the description.
    hard = _match(title, HARD_PATTERNS)
    if employment_type and _INTERN_TYPE.search(employment_type) and "intern" not in hard:
        hard.append("intern")
    if not hard:
        return False, []

    # TECH gate: relevance signal, may scan title + description.
    text = " ".join(p for p in (title, description) if p)
    orbag = _match(text, ORBAG_PATTERNS)
    if not orbag:
        return False, []

    return True, sorted(set(hard + orbag))

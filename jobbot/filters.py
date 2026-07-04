"""Student-role keyword filter (applied by Refresh, Component B).

A job passes only if BOTH gates hit:
  HARD   : a student-role term (intern / co-op / new-grad / early-career) in the
           TITLE, OR a structured employment-type signal from the ATS
           (Lever commitment, Ashby employmentType).
  OR-BAG : at least one PROFESSIONAL-FIELD term anywhere in title OR description.
           No longer tech-only — covers engineering (all disciplines), the
           physical & life sciences, health/medicine, and quantitative / finance /
           business / marketing. Its only job now is to keep out non-professional
           student roles (retail, food service, camp, etc.).

CRITICAL: the HARD gate reads the TITLE only, never the description. Full-time
senior roles routinely mention "interns"/"co-op"/"early career" in description
boilerplate (mentoring blurbs, benefits/EEO sections) — matching that turned
~every job at Stripe/OpenAI into a false "intern". Real student roles say so in
the title or are tagged by the ATS. The field OR-bag is only a relevance signal,
so it may scan the description — which makes it deliberately permissive (a broad
field bag + description scan surfaces cross-disciplinary roles). If field noise
creeps in, the tightening knob is to match the OR-bag on the TITLE only.

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

# (label, pattern) — labels feed listings.keywords_matched, so keep them
# display-friendly. Grouped by field family for readability.
ORBAG_PATTERNS = [
    # --- software / CS / data ---
    ("software", re.compile(r"\bsoftware\b", re.I)),
    ("developer", re.compile(r"\bdevelop(er|ment)?\b", re.I)),
    ("AI", re.compile(r"\b(ai|artificial intelligence)\b", re.I)),
    ("ML", re.compile(r"\b(ml|machine learning)\b", re.I)),
    ("data", re.compile(r"\bdata\b", re.I)),
    ("computer science", re.compile(r"\bcomputer science\b", re.I)),
    ("security", re.compile(r"\b(cyber\s?security|infosec)\b", re.I)),
    ("cloud", re.compile(r"\b(cloud|devops|sre)\b", re.I)),
    # --- engineering (all disciplines) ---
    ("engineering", re.compile(r"\bengineer(ing|s)?\b", re.I)),
    ("mechanical", re.compile(r"\bmechanical\b", re.I)),
    ("electrical", re.compile(r"\belectrical\b", re.I)),
    ("aerospace", re.compile(r"\b(aerospace|aeronautical|astronautical|avionics)\b", re.I)),
    ("chemical eng", re.compile(r"\bchemical engineer", re.I)),
    ("civil", re.compile(r"\bcivil engineer", re.I)),
    ("biomedical", re.compile(r"\b(biomedical|bioengineer(ing)?|biomechanical)\b", re.I)),
    ("robotics", re.compile(r"\b(robotics?|mechatronics)\b", re.I)),
    ("hardware", re.compile(r"\b(hardware|firmware|embedded|fpga|asic)\b", re.I)),
    ("industrial", re.compile(r"\b(industrial|manufacturing)\b", re.I)),
    ("automotive", re.compile(r"\bautomotive\b", re.I)),
    # "controls"/"materials" alone are boilerplate magnets ("cost controls",
    # "marketing materials") — require the engineering/science context.
    ("controls", re.compile(r"\bcontrol(s| systems?) engineer", re.I)),
    ("materials science", re.compile(r"\bmaterials scien(ce|tist)\b", re.I)),
    # --- physical & life sciences ---
    ("physics", re.compile(r"\bphysics?\b", re.I)),
    ("chemistry", re.compile(r"\b(chemistry|chemist)\b", re.I)),
    ("biology", re.compile(r"\b(biology|biologist|molecular|genomics?|genetics)\b", re.I)),
    ("biotech", re.compile(r"\b(biotech(nology)?|bioinformatics|life sciences?)\b", re.I)),
    ("neuroscience", re.compile(r"\bneuroscience\b", re.I)),
    ("research", re.compile(r"\bresearch\b", re.I)),
    ("laboratory", re.compile(r"\blab(oratory)?\b", re.I)),
    # --- health / medicine ---
    ("medical", re.compile(r"\b(medical|medicine|clinical|health\s?care|pharmaceutical|pharma)\b", re.I)),
    # --- quantitative / finance / business ---
    ("finance", re.compile(r"\b(finance|financial)\b", re.I)),
    ("quant", re.compile(r"\b(quant|quantitative)\b", re.I)),
    ("accounting", re.compile(r"\b(accounting|accountant|audit(ing)?|taxation)\b", re.I)),
    ("economics", re.compile(r"\b(economics?|econometrics)\b", re.I)),
    ("investment", re.compile(r"\b(investment|banking|trading|trader|private equity|asset management)\b", re.I)),
    ("actuarial", re.compile(r"\bactuar(ial|y)\b", re.I)),
    ("consulting", re.compile(r"\bconsult(ing|ant)\b", re.I)),
    ("business", re.compile(r"\b(business|operations|strategy)\b", re.I)),
    ("supply chain", re.compile(r"\b(supply chain|logistics|procurement)\b", re.I)),
    ("analytics", re.compile(r"\b(analytics|analyst|statistics|statistical)\b", re.I)),
    ("mathematics", re.compile(r"\bmathematic(s|al)\b", re.I)),
    # --- marketing / communications / product / design ---
    ("marketing", re.compile(r"\bmarketing\b", re.I)),
    # plural only — the field ("Corporate Communications"); singular "communication"
    # is almost always the "strong communication skills" boilerplate.
    ("communications", re.compile(r"\bcommunications\b", re.I)),
    ("advertising", re.compile(r"\b(advertising|public relations|branding)\b", re.I)),
    ("product", re.compile(r"\bproduct manage(r|ment)\b", re.I)),
    ("design", re.compile(r"\b(design(er)?|ux|ui)\b", re.I)),
    ("sales", re.compile(r"\b(sales|business development)\b", re.I)),
]

# Matches the ATS employment-type controlled vocab ("Intern", "Internship").
# Prefix match (no trailing \b) so "Internship" is caught; the field is a
# controlled vocabulary so there's no "internal"-style false positive risk here.
_INTERN_TYPE = re.compile(r"\bintern", re.I)


def _match(text: str, patterns) -> list[str]:
    return [label for label, pat in patterns if pat.search(text)]


def hard_gate(title: str, employment_type: str = "") -> list[str]:
    """Student-role labels from the HARD gate: TITLE + structured employment type
    ONLY, never the description (see module note). An empty result means the job
    can NEVER pass evaluate(), so callers can use it as a cheap necessary-condition
    pre-check (e.g. skip an expensive per-job description fetch)."""
    hard = _match(title or "", HARD_PATTERNS)
    if employment_type and _INTERN_TYPE.search(employment_type) and "intern" not in hard:
        hard.append("intern")
    return hard


def evaluate(title: str, description: str = "", employment_type: str = "") -> tuple[bool, list[str]]:
    """Return (passes, matched_labels)."""
    title = title or ""

    # HARD gate: TITLE only (+ structured employment type). Never the description.
    hard = hard_gate(title, employment_type)
    if not hard:
        return False, []

    # TECH gate: relevance signal, may scan title + description.
    text = " ".join(p for p in (title, description) if p)
    orbag = _match(text, ORBAG_PATTERNS)
    if not orbag:
        return False, []

    return True, sorted(set(hard + orbag))

from .domains import SEED_DOMAINS

# Field slices for seed discovery (only used when re-burning Serper — steady-state
# company growth is Common Crawl, which ignores these). Broadened past tech to pull
# in engineering, life-science, health, and finance/business employers too.
FIELD_TERMS = [
    # software / data
    "software engineer",
    "data",
    "machine learning",
    "artificial intelligence",
    "computer science",
    "cybersecurity",
    # engineering (disciplines)
    "mechanical engineering",
    "electrical engineering",
    "aerospace",
    "chemical engineering",
    "civil engineering",
    "biomedical engineering",
    "materials science",
    "robotics",
    "hardware",
    "automotive",
    "manufacturing",
    # physical & life sciences
    "physics",
    "chemistry",
    "biology",
    "biotech",
    "neuroscience",
    "research scientist",
    # health / medicine
    "medical device",
    "clinical",
    "pharmaceutical",
    # quantitative / finance / business
    "quantitative",
    "finance",
    "accounting",
    "economics",
    "investment banking",
    "actuarial",
    "consulting",
    "operations",
    "supply chain",
    "business development",
    # marketing / comms / product / design
    "marketing",
    "communications",
    "sales",
    "product manager",
    "product designer",
]


def build_queries(domains=None, fields=None, include_bare=True):
    domains = domains or SEED_DOMAINS
    fields = fields or FIELD_TERMS
    out = []
    for domain, ats, _slug_in in domains:
        if include_bare:
            out.append({"q": f"site:{domain}", "domain": domain, "ats": ats, "field": ""})
        for f in fields:
            out.append({"q": f"site:{domain} {f}", "domain": domain, "ats": ats, "field": f})
    return out


#for dry run only, not important
DRYRUN_SAMPLE = [
    {"q": "site:boards.greenhouse.io software engineer", "domain": "boards.greenhouse.io", "ats": "greenhouse", "field": "software engineer"},
    {"q": "site:jobs.lever.co machine learning", "domain": "jobs.lever.co", "ats": "lever", "field": "machine learning"},
    {"q": "site:jobs.ashbyhq.com quantitative", "domain": "jobs.ashbyhq.com", "ats": "ashby", "field": "quantitative"},
    {"q": "site:teamtailor.com robotics", "domain": "teamtailor.com", "ats": "teamtailor", "field": "robotics"},
    {"q": "site:myworkdayjobs.com aerospace", "domain": "myworkdayjobs.com", "ats": "workday", "field": "aerospace"},
]

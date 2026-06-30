from .domains import SEED_DOMAINS

FIELD_TERMS = [
    "software engineer",
    "data",
    "machine learning",
    "artificial intelligence",
    "quantitative",
    "finance",
    "mechanical engineering",
    "electrical engineering",
    "aerospace",
    "robotics",
    "hardware",
    "medical device",
    "biotech",
    "computer science",
    "research scientist",
    "product manager",
    "sales",
    "marketing",
    "operations",
    "business development",
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

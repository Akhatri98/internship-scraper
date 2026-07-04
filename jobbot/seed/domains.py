"""ATS domains for the one-time seed + best-effort slug extraction.

This is DISCOVERY-only and intentionally broader than the runtime registry
(jobbot/ats/registry.py): we capture slugs for ATSs we can't poll yet (no
Refresh adapter until Stage 6). The raw JSONL capture preserves ground truth, so
imperfect long-tail parsing here is recoverable without re-spending queries.

slug_in:
  "path"      -> first path segment is the slug   (boards.greenhouse.io/<slug>)
  "subdomain" -> leading label is the slug         (<slug>.teamtailor.com)

For subdomain ATSs the `domain` is the BASE domain so `site:<domain>` sweeps all
company subdomains.
"""
import re
from urllib.parse import urlsplit

# (domain_for_site_query, ats_source, slug_in)
SEED_DOMAINS = [
    ("boards.greenhouse.io", "greenhouse", "path"),
    ("job-boards.greenhouse.io", "greenhouse", "path"),
    ("jobs.lever.co", "lever", "path"),
    ("jobs.ashbyhq.com", "ashby", "path"),
    ("jobs.smartrecruiters.com", "smartrecruiters", "path"),
    ("apply.workable.com", "workable", "path"),
    ("jobs.jobvite.com", "jobvite", "path"),
    ("ats.rippling.com", "rippling", "path"),
    ("myworkdayjobs.com", "workday", "subdomain"),
    ("icims.com", "icims", "subdomain"),
    ("teamtailor.com", "teamtailor", "subdomain"),
    ("bamboohr.com", "bamboohr", "subdomain"),
    ("breezy.hr", "breezy", "subdomain"),
    ("recruitee.com", "recruitee", "subdomain"),
    ("applytojob.com", "jazzhr", "subdomain"),  # JazzHR (name != URL)
    ("zohorecruit.com", "zohorecruit", "subdomain"),
]

# Subdomain/path labels that are never a company slug.
_GENERIC = {
    "www", "careers", "career", "jobs", "job", "apply", "app", "api", "help",
    "support", "info", "blog", "status", "go", "my", "secure", "hire", "talent",
    "work", "embed", "boards", "static", "cdn", "assets",
}


def _host(url: str) -> str:
    netloc = urlsplit(url).netloc.lower()
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    return netloc.split(":", 1)[0]


# Workday URL path may lead with a locale ("en-US", "fr", "en-GB") before the site.
_WD_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2})?$", re.I)
# Path segments that are never a Workday career-site name.
_WD_NOT_SITE = {"wday", "job", "jobs", "login", "search"}


def _workday_slug(url: str, host: str, domain: str):
    """Workday needs a COMPOSITE slug "tenant.wdN/Site" — the CXS poll endpoint
    requires tenant + datacenter host + career-site name, so a bare tenant is
    useless. Returns None when the URL doesn't reveal the site (e.g. bare host)."""
    label = host[: -len(domain)].rstrip(".")  # e.g. "blueorigin.wd5"
    if "." not in label:
        return None  # no wdN — can't reconstruct the API host
    tenant = label.split(".")[0]
    if not tenant or tenant in _GENERIC:
        return None
    segs = [s for s in urlsplit(url).path.split("/") if s]
    if segs and _WD_LOCALE.fullmatch(segs[0]):
        segs = segs[1:]
    if not segs or segs[0].lower() in _WD_NOT_SITE:
        return None
    return "workday", f"{label.lower()}/{segs[0]}"  # site name keeps its case


def extract(url: str):
    """Return (ats_source, slug) or None if no confident slug."""
    host = _host(url)
    for domain, ats, slug_in in SEED_DOMAINS:
        if slug_in == "path":
            if host != domain:
                continue
            segs = [s for s in urlsplit(url).path.split("/") if s]
            if not segs:
                return None
            slug = segs[0].lower()
            return (ats, slug) if slug not in _GENERIC else None
        else:  # subdomain
            if host != domain and not host.endswith("." + domain):
                continue
            if ats == "workday":
                return _workday_slug(url, host, domain)
            label = host[: -len(domain)].rstrip(".")  # everything before the base
            if not label:
                return None  # bare base domain, no company
            parts = [p for p in label.split(".") if p not in _GENERIC]
            if not parts:
                return None
            return ats, parts[0].lower()
    return None

from ..util import ms_to_iso, strip_html, display_name
from ..geo import country_of
from ..pay import format_salary
from .parse import normalize_url

_GH_CANONICAL = "https://job-boards.greenhouse.io/{slug}/jobs/{jid}"


def _join(*parts) -> str:
    """Comma-join the truthy string parts into a "City, Region" location label."""
    return ", ".join(p for p in parts if isinstance(p, str) and p.strip())


def greenhouse_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("jobs", []):
        jid = j.get("id")
        if jid is None:
            continue
        loc = (j.get("location") or {}).get("name") or ""  # free text, e.g. "London, UK"
        out.append({
            "canonical_url": _GH_CANONICAL.format(slug=slug, jid=jid),
            "raw_url": j.get("absolute_url"),
            "title": j.get("title") or "",
            "description": strip_html(j.get("content")),
            "posted_at": j.get("first_published") or j.get("updated_at"),
            "employment_type": "",  # greenhouse endpt dont expose it
            "location": loc,
            "country": country_of(location=loc),
            "company": j.get("company_name") or fallback,   # real name per job
            "pay": None,                                     # not in list endpoint -> unpaid check in _build_rows
        })
    return out


def lever_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    if not isinstance(data, list):
        return out
    for j in data:
        url = j.get("hostedUrl")
        if not url:
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""  # free text, e.g. "New York, NY"
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("text") or "",
            "description": j.get("descriptionPlain") or "",
            "posted_at": ms_to_iso(j.get("createdAt")),
            "employment_type": cats.get("commitment") or "",
            "location": loc,
            "country": country_of(j.get("country"), loc),  # lever exposes a top-level country
            "company": fallback,                           # no company name in feed
            "pay": None,
        })
    return out


def ashby_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        url = j.get("jobUrl") or j.get("applyUrl")
        if not url:
            continue
        loc = j.get("location") or ""
        cc = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
        comp = j.get("compensation") or {}
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": j.get("descriptionPlain") or "",
            "posted_at": j.get("publishedAt"),
            "employment_type": j.get("employmentType") or "",
            "location": loc,
            "country": country_of(cc, loc),
            "company": fallback,  # ashby feed carries no org name
            # we fetch includeCompensation=true; the summary is a ready display string
            "pay": comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary"),
        })
    return out


def _label(d):
    return (d or {}).get("label") or (d or {}).get("name") or "" if isinstance(d, dict) else ""


def smartrecruiters_jobs(data, slug):
    # note no disc in endpt
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("content", []):
        jid = j.get("id")
        if jid is None:
            continue
        desc = " ".join(x for x in (_label(j.get("department")), _label(j.get("function"))) if x)
        lj = j.get("location") or {}  # {city, region, country (ISO2), remote}
        out.append({
            "canonical_url": f"https://jobs.smartrecruiters.com/{slug}/{jid}",
            "raw_url": f"https://jobs.smartrecruiters.com/{slug}/{jid}",
            "title": j.get("name") or "",
            "description": desc,
            "posted_at": j.get("releasedDate"),
            "employment_type": _label(j.get("typeOfEmployment")),
            "location": _join(lj.get("city"), lj.get("region")),
            "country": country_of(lj.get("country"), _join(lj.get("city"), lj.get("region"))),
            "company": (j.get("company") or {}).get("name") or fallback,  # real name per job
            "pay": None,
        })
    return out


def workable_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("results", []):
        sc = j.get("shortcode")
        if not sc:
            continue
        depts = j.get("department") or []
        lj = j.get("location") or {}  # {country, countryCode, city, region, ...}
        out.append({
            "canonical_url": f"https://apply.workable.com/{slug}/j/{sc}",
            "raw_url": f"https://apply.workable.com/{slug}/j/{sc}",
            "title": j.get("title") or "",
            "description": " ".join(d for d in depts if isinstance(d, str)),
            "posted_at": j.get("published"),
            "employment_type": j.get("type") or "",
            "location": _join(lj.get("city"), lj.get("region")),
            "country": country_of(lj.get("country") or lj.get("countryCode"),
                                  _join(lj.get("city"), lj.get("region"))),
            "company": fallback,
            "pay": None,
        })
    return out


def breezy_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in data if isinstance(data, list) else []:
        url = j.get("url")
        if not url:
            continue
        dept = j.get("department")
        lj = j.get("location") or {}
        country = lj.get("country")
        country = country.get("name") if isinstance(country, dict) else country
        loc = lj.get("name") or _join(lj.get("city"),
                                      _label(lj.get("state")) or (lj.get("state") if isinstance(lj.get("state"), str) else ""))
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("name") or "",
            "description": dept if isinstance(dept, str) else "",
            "posted_at": j.get("published_date"),
            "employment_type": _label(j.get("type")),
            "location": loc,
            "country": country_of(country, loc),
            "company": fallback,
            "pay": None,
        })
    return out


def recruitee_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("offers", []):
        url = j.get("careers_url")
        if not url:
            continue
        desc = strip_html(" ".join(x for x in (j.get("description"), j.get("requirements")) if x))
        loc = j.get("location") or _join(j.get("city"), j.get("state_name") or j.get("region"))
        sal = j.get("salary") or {}
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": desc,
            "posted_at": j.get("published_at"),
            "employment_type": j.get("employment_type_code") or "",
            "location": loc,
            "country": country_of(j.get("country") or j.get("country_code"), loc),
            "company": j.get("company_name") or fallback,  # real name per offer
            "pay": format_salary(sal.get("min"), sal.get("max"), sal.get("period"), sal.get("currency")),
        })
    return out


def rippling_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in data if isinstance(data, list) else []:
        url = j.get("url")
        if not url:
            continue
        loc = j.get("workLocation") or _label(j.get("location"))
        if not loc:
            locs = j.get("locations")
            if isinstance(locs, list) and locs:
                loc = _label(locs[0]) or (locs[0] if isinstance(locs[0], str) else "")
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("name") or "",
            "description": _label(j.get("department")),
            "posted_at": None,
            "employment_type": "",
            "location": loc or "",
            "country": country_of(location=loc or None),
            "company": fallback,
            "pay": None,
        })
    return out


def teamtailor_jobs(data, slug):
    out = []
    # teamtailor reports the company name once, at the feed level ("title")
    company = (data or {}).get("title") or display_name(slug)
    for j in (data or {}).get("items", []):
        url = j.get("url")
        if not url:
            continue
        loc = j.get("location") if isinstance(j.get("location"), str) else ""
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": strip_html(j.get("content_html")),
            "posted_at": j.get("date_published"),
            "employment_type": "",
            "location": loc,
            "country": country_of(location=loc or None),
            "company": company,
            "pay": None,
        })
    return out


ADAPTERS = {
    "greenhouse": greenhouse_jobs,
    "lever": lever_jobs,
    "ashby": ashby_jobs,
    "smartrecruiters": smartrecruiters_jobs,
    "workable": workable_jobs,
    "breezy": breezy_jobs,
    "recruitee": recruitee_jobs,
    "rippling": rippling_jobs,
    "teamtailor": teamtailor_jobs,
}

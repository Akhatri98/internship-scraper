import re
from datetime import datetime, timedelta, timezone
from ..util import ms_to_iso, strip_html, display_name
from ..geo import country_of
from ..pay import format_salary
from ..filters import hard_gate
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


def _tt_location(jp):
    """(location, country) from the first jobLocation in teamtailor's embedded
    schema.org _jobposting. jobLocation is a list of {address: PostalAddress};
    the top-level item.location is ~always absent, so this is where it lives."""
    jl = jp.get("jobLocation")
    if isinstance(jl, dict):
        jl = [jl]
    addr = (jl[0].get("address") if jl and isinstance(jl[0], dict) else None) or {}
    loc = _join(addr.get("addressLocality"), addr.get("addressRegion"))
    return loc, country_of(addr.get("addressCountry"), loc)


def _tt_pay(jp):
    """teamtailor baseSalary (schema.org MonetaryAmount) -> display string.
    value is either {value} (single) or {minValue, maxValue}; unitText is the
    period (YEAR/MONTH/DAY/HOUR)."""
    bs = jp.get("baseSalary") or {}
    val = bs.get("value") or {}
    return format_salary(val.get("minValue") or val.get("value"), val.get("maxValue"),
                         (val.get("unitText") or "").lower(), bs.get("currency"))


def teamtailor_jobs(data, slug):
    out = []
    # teamtailor reports the company name once, at the feed level ("title")
    company = (data or {}).get("title") or display_name(slug)
    for j in (data or {}).get("items", []):
        url = j.get("url")
        if not url:
            continue
        jp = j.get("_jobposting") or {}   # embedded schema.org JobPosting — richer than top level
        loc = j.get("location") if isinstance(j.get("location"), str) else ""
        country = country_of(location=loc or None)
        if not loc:                       # recover loc + ISO2 country from _jobposting
            loc, country = _tt_location(jp)
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": strip_html(j.get("content_html")) or strip_html(jp.get("description")),
            "posted_at": j.get("date_published") or jp.get("datePosted"),
            "employment_type": "",
            "location": loc,
            "country": country,
            "company": company,
            "pay": _tt_pay(jp),
        })
    return out


def bamboohr_jobs(data, slug):
    out = []
    fallback = display_name(slug)
    for j in (data or {}).get("result", []):
        jid = j.get("id")
        if jid is None:
            continue
        lj = j.get("atsLocation") or j.get("location") or {}
        loc = _join(lj.get("city"), lj.get("state") or lj.get("province"))
        if not loc and j.get("isRemote"):
            loc = "Remote"
        out.append({
            "canonical_url": f"https://{slug}.bamboohr.com/careers/{jid}",
            "raw_url": f"https://{slug}.bamboohr.com/careers/{jid}",
            "title": j.get("jobOpeningName") or "",
            "description": j.get("departmentLabel") or "",
            "posted_at": None,  # list endpoint carries no post date
            "employment_type": j.get("employmentStatusLabel") or "",
            "location": loc,
            "country": country_of(lj.get("country"), loc),
            "company": fallback,
            "pay": None,
        })
    return out

_JAZZ_LINK = re.compile(r'<a\s+href="(https://[^"]+/apply/([A-Za-z0-9]+))[^"]*"\s*>\s*(.*?)\s*</a>', re.S)
_JAZZ_LOC = re.compile(r'fa-map-marker[\'"]>\s*</i>\s*([^<]+)')


def jazzhr_jobs(html_text, slug):
    out = []
    fallback = display_name(slug)
    for chunk in (html_text or "").split("list-group-item-heading")[1:]:
        m = _JAZZ_LINK.search(chunk)
        if not m:
            continue
        _, jid, title = m.groups()
        lm = _JAZZ_LOC.search(chunk[:1500])  # location <ul> directly follows the heading
        loc = strip_html(lm.group(1)) if lm else ""
        out.append({
            "canonical_url": f"https://{slug}.applytojob.com/apply/{jid}",
            "raw_url": m.group(1),
            "title": strip_html(title),
            "description": "",
            "posted_at": None,
            "employment_type": "",
            "location": loc,
            "country": country_of(location=loc or None),
            "company": fallback,
            "pay": None,
        })
    return out


_JV_ROW = re.compile(
    r'<td class="jv-job-list-name">\s*<a href="(/[^"/]+/job/([^"]+))"\s*>(.*?)</a>\s*</td>\s*'
    r'<td class="jv-job-list-location">\s*(.*?)\s*</td>', re.S)


def jobvite_jobs(html_pages, slug):
    out = []
    fallback = display_name(slug)
    for page in html_pages if isinstance(html_pages, list) else [html_pages]:
        for path, jid, title, loc in _JV_ROW.findall(page or ""):
            loc = strip_html(loc)
            out.append({
                "canonical_url": f"https://jobs.jobvite.com/{slug}/job/{jid}",
                "raw_url": f"https://jobs.jobvite.com{path}",
                "title": strip_html(title),
                "description": "",
                "posted_at": None,
                "employment_type": "",
                "location": loc,
                "country": country_of(location=loc or None),
                "company": fallback,
                "pay": None,
            })
    return out


_WD_POSTED = re.compile(r"posted\s+(today|yesterday|(\d+)\s+days?\s+ago)", re.I)


def _workday_posted(text):
    """'Posted Yesterday' / 'Posted 3 Days Ago' -> ISO date (day resolution).
    '30+ Days Ago' -> None (unknown, could be far older)."""
    m = _WD_POSTED.search(text or "")
    if not m:
        return None
    word = m.group(1).lower()
    days = 0 if word == "today" else 1 if word == "yesterday" else int(m.group(2))
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _wd_country(info):
    """Country descriptor from a CXS detail's jobPostingInfo. `country` is a
    {descriptor, id} object; geo.country_of normalizes "United States of
    America" & friends to a display name."""
    c = info.get("country")
    return c.get("descriptor") if isinstance(c, dict) else (c if isinstance(c, str) else None)


def workday_jobs(postings, slug):
    # slug is composite "tenant.wdN/Site"; postings are CXS jobPostings dicts.
    # A posting the fetcher enriched carries its CXS detail under "_detail"
    # (real description + exact country + real posted date); without it we fall
    # back to the list-level fields (empty desc, free-text loc, relative date).
    hostpart, _, site = (slug or "").partition("/")
    base = f"https://{hostpart}.myworkdayjobs.com"
    fallback = display_name(hostpart.split(".")[0])
    out = []
    for p in postings if isinstance(postings, list) else []:
        path = p.get("externalPath")
        if not path:
            continue
        info = p.get("_detail") or {}
        loc = info.get("location") or p.get("locationsText") or ""
        out.append({
            "canonical_url": f"{base}/en-US/{site}{path}",
            "raw_url": f"{base}/en-US/{site}{path}",
            "title": p.get("title") or "",
            "description": strip_html(info.get("jobDescription")) if info.get("jobDescription") else "",
            "posted_at": info.get("startDate") or _workday_posted(p.get("postedOn")),
            "employment_type": "",
            "location": loc,
            "country": country_of(_wd_country(info), loc),
            "company": fallback,
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
    "bamboohr": bamboohr_jobs,
}


def workable_fetch(slug, req):
    """POST board API pages via nextPage token (server-fixed 10 results/page)."""
    api = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
    results, token = [], None
    for _ in range(150):  # cap: 1500 jobs
        d = req(api, method="POST", body={"token": token} if token else {}).json() or {}
        page = d.get("results") or []
        results.extend(page)
        token = d.get("nextPage")
        if not token or not page:
            break
    return workable_jobs({"results": results}, slug)


# canonical_urls (keyed by ATS) that already carry a real, detail-fetched
# description, so a fetcher can skip re-enriching them. refresh.run_refresh
# preloads this per run; an ATS absent here (tests / plain CLI) => enrich every
# match. Used by the detail-enriching fetchers (smartrecruiters, workday).
_ENRICHED: dict[str, set[str]] = {}


def set_enriched(ats: str, urls) -> None:
    _ENRICHED[ats] = set(urls or ())


def _is_enriched(ats: str, canonical_url) -> bool:
    return canonical_url in _ENRICHED.get(ats, ())


def _sr_detail_desc(detail) -> str:
    """Real job description from a SmartRecruiters posting-detail payload.
    The LIST endpoint only carries dept/function labels; the DETAIL endpoint has
    the actual text under jobAd.sections.{jobDescription,qualifications,...}."""
    secs = ((detail or {}).get("jobAd") or {}).get("sections") or {}
    parts = [(secs.get(k) or {}).get("text", "")
             for k in ("jobDescription", "qualifications", "additionalInformation")]
    return strip_html(" ".join(p for p in parts if p))


def smartrecruiters_fetch(slug, req):
    """GET posting pages via offset (limit maxes out at 100), then enrich the
    student-role postings' descriptions from the per-posting detail endpoint.

    The list endpoint omits descriptions, so a matched listing would otherwise
    store a bare "Engineering" snippet. We fetch detail ONLY for postings that
    clear the title-only HARD gate (a necessary condition for evaluate(), so
    non-student roles are never fetched) and that we haven't already stored a
    description for — bounding the extra requests to genuinely new matches."""
    api = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    content, offset, total = [], 0, None
    for _ in range(50):  # cap: 5000 postings
        d = req(f"{api}?limit=100&offset={offset}").json() or {}
        page = d.get("content") or []
        content.extend(page)
        total = d.get("totalFound") or 0
        offset += len(page)
        if not page or offset >= total:
            break
    jobs = smartrecruiters_jobs({"content": content}, slug)
    for job in jobs:
        canon = job.get("canonical_url")
        if _is_enriched("smartrecruiters", canon) or \
                not hard_gate(job.get("title") or "", job.get("employment_type") or ""):
            continue
        jid = (canon or "").rsplit("/", 1)[-1]
        try:
            desc = _sr_detail_desc(req(f"{api}/{jid}").json())
        except Exception:  # noqa: BLE001 — a detail failure just keeps the thin label
            continue
        if desc:
            job["description"] = desc
    return jobs


def jobvite_fetch(slug, req):
    """GET search pages (?p= is 0-indexed, 50 rows each) until a short page."""
    pages = []
    for p in range(40):  # cap: 2000 jobs
        html = req(f"https://jobs.jobvite.com/{slug}/search?q=&p={p}").text
        n_before = len(_JV_ROW.findall(html))
        pages.append(html)
        if n_before < 50:
            break
    return jobvite_jobs(pages, slug)

_WD_SEARCH_TERMS = ("intern", "co-op", "new grad", "early career")


def workday_fetch(slug, req):
    hostpart, _, site = (slug or "").partition("/")
    if not site:
        # Bare legacy slug (no career-site name) — CXS is unreachable. Treated
        # as a poll error upstream; the repair/discovery path supplies composites.
        raise ValueError(f"workday slug missing site: {slug!r}")
    tenant = hostpart.split(".")[0]
    base = f"https://{hostpart}.myworkdayjobs.com"
    cxs = f"{base}/wday/cxs/{tenant}/{site}"
    seen = {}
    for term in _WD_SEARCH_TERMS:
        offset, total = 0, None
        for _ in range(25):  # cap: 500 postings per term
            d = req(f"{cxs}/jobs", method="POST",
                    body={"limit": 20, "offset": offset, "searchText": term}).json() or {}
            page = d.get("jobPostings") or []
            if total is None:
                total = d.get("total") or 0  # only the first page reports total
            for p in page:
                if p.get("externalPath"):
                    seen.setdefault(p["externalPath"], p)
            offset += len(page)
            if not page or offset >= total:
                break
    # Enrich: the CXS list is title-only, but GET {cxs}{externalPath} returns the
    # real description PLUS an exact country and a real posted date (startDate) —
    # fixing workday's two other weak fields, not just the empty snippet. Fetch
    # only for student-title matches we haven't already stored (see _ENRICHED).
    postings = list(seen.values())
    for p in postings:
        canon = f"{base}/en-US/{site}{p['externalPath']}"
        if _is_enriched("workday", canon) or not hard_gate(p.get("title") or ""):
            continue
        try:
            p["_detail"] = (req(f"{cxs}{p['externalPath']}").json() or {}).get("jobPostingInfo") or {}
        except Exception:  # noqa: BLE001 — detail failure keeps the list-level fields
            continue
    return workday_jobs(postings, slug)


def jazzhr_fetch(slug, req):
    """Single server-rendered page listing every opening."""
    return jazzhr_jobs(req(f"https://{slug}.applytojob.com/apply/").text, slug)


FETCHERS = {
    "workable": workable_fetch,
    "smartrecruiters": smartrecruiters_fetch,
    "jobvite": jobvite_fetch,
    "workday": workday_fetch,
    "jazzhr": jazzhr_fetch,
}
POLLABLE = set(ADAPTERS) | set(FETCHERS)

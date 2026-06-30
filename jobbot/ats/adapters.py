from ..util import ms_to_iso, strip_html
from .parse import normalize_url

_GH_CANONICAL = "https://job-boards.greenhouse.io/{slug}/jobs/{jid}"


def greenhouse_jobs(data, slug):
    out = []
    for j in (data or {}).get("jobs", []):
        jid = j.get("id")
        if jid is None:
            continue
        out.append({
            "canonical_url": _GH_CANONICAL.format(slug=slug, jid=jid),
            "raw_url": j.get("absolute_url"),
            "title": j.get("title") or "",
            "description": strip_html(j.get("content")),
            "posted_at": j.get("first_published") or j.get("updated_at"),
            "employment_type": "",  # greenhouse endpt dont expose it
        })
    return out


def lever_jobs(data, _):
    out = []
    if not isinstance(data, list):
        return out
    for j in data:
        url = j.get("hostedUrl")
        if not url:
            continue
        cats = j.get("categories") or {}
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("text") or "",
            "description": j.get("descriptionPlain") or "",
            "posted_at": ms_to_iso(j.get("createdAt")),
            "employment_type": cats.get("commitment") or "",
        })
    return out


def ashby_jobs(data, _):
    out = []
    for j in (data or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        url = j.get("jobUrl") or j.get("applyUrl")
        if not url:
            continue
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": j.get("descriptionPlain") or "",
            "posted_at": j.get("publishedAt"),
            "employment_type": j.get("employmentType") or "",
        })
    return out


def _label(d):
    return (d or {}).get("label") or (d or {}).get("name") or "" if isinstance(d, dict) else ""


def smartrecruiters_jobs(data, slug):
    # note no disc in endpt
    out = []
    for j in (data or {}).get("content", []):
        jid = j.get("id")
        if jid is None:
            continue
        desc = " ".join(x for x in (_label(j.get("department")), _label(j.get("function"))) if x)
        out.append({
            "canonical_url": f"https://jobs.smartrecruiters.com/{slug}/{jid}",
            "raw_url": f"https://jobs.smartrecruiters.com/{slug}/{jid}",
            "title": j.get("name") or "",
            "description": desc,
            "posted_at": j.get("releasedDate"),
            "employment_type": _label(j.get("typeOfEmployment")),
        })
    return out


def workable_jobs(data, slug):
    out = []
    for j in (data or {}).get("results", []):
        sc = j.get("shortcode")
        if not sc:
            continue
        depts = j.get("department") or []
        out.append({
            "canonical_url": f"https://apply.workable.com/{slug}/j/{sc}",
            "raw_url": f"https://apply.workable.com/{slug}/j/{sc}",
            "title": j.get("title") or "",
            "description": " ".join(d for d in depts if isinstance(d, str)),
            "posted_at": j.get("published"),
            "employment_type": j.get("type") or "",
        })
    return out


def breezy_jobs(data, _):
    out = []
    for j in data if isinstance(data, list) else []:
        url = j.get("url")
        if not url:
            continue
        dept = j.get("department")
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("name") or "",
            "description": dept if isinstance(dept, str) else "",
            "posted_at": j.get("published_date"),
            "employment_type": _label(j.get("type")),
        })
    return out


def recruitee_jobs(data, _):
    out = []
    for j in (data or {}).get("offers", []):
        url = j.get("careers_url")
        if not url:
            continue
        desc = strip_html(" ".join(x for x in (j.get("description"), j.get("requirements")) if x))
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": desc,
            "posted_at": j.get("published_at"),
            "employment_type": j.get("employment_type_code") or "",
        })
    return out


def rippling_jobs(data, _):
    out = []
    for j in data if isinstance(data, list) else []:
        url = j.get("url")
        if not url:
            continue
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("name") or "",
            "description": _label(j.get("department")),
            "posted_at": None,
            "employment_type": "",
        })
    return out


def teamtailor_jobs(data, _):
    out = []
    for j in (data or {}).get("items", []):
        url = j.get("url")
        if not url:
            continue
        out.append({
            "canonical_url": normalize_url(url),
            "raw_url": url,
            "title": j.get("title") or "",
            "description": strip_html(j.get("content_html")),
            "posted_at": j.get("date_published"),
            "employment_type": "",
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

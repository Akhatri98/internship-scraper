"""Refresh (Component B): poll each company's ATS public JSON, filter to student
tech roles, upsert into listings. Runs 2x/day in production (Stage 5).

Hardening baked in: per-call retry/backoff, per-company log-and-continue, and a
404 flips companies.still_active = false so we stop polling dead boards.
"""
import time

import requests

from . import db
from .ats.adapters import ADAPTERS
from .ats.registry import ATS
from .filters import evaluate
from .util import now_iso

_UA = {"User-Agent": "job-bot/0.1 (+https://github.com/Akhatri98/Job-Bot)",
       "Accept": "application/json"}


def _request(url, session, method="GET", body=None, attempts=3):
    """HTTP with retry/backoff on transient failures. 4xx raises immediately
    (e.g. 404 -> caller marks the board inactive)."""
    last = None
    for i in range(attempts):
        try:
            if method == "POST":
                r = session.post(url, headers={**_UA, "Content-Type": "application/json"},
                                 json=body or {}, timeout=30)
            else:
                r = session.get(url, headers=_UA, timeout=30)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            time.sleep(0.5 * (2 ** i))
            continue
        if r.status_code >= 500:
            last = requests.HTTPError(f"{r.status_code} server error", response=r)
            time.sleep(0.5 * (2 ** i))
            continue
        r.raise_for_status()  # 4xx -> raise now, no retry
        return r
    raise last


def fetch_jobs(slug, ats, session):
    cfg = ATS[ats]
    r = _request(cfg["api"].format(slug=slug), session, method=cfg.get("method", "GET"))
    data = r.json() if r.text else {}
    return ADAPTERS[ats](data, slug)


def _build_rows(jobs, slug, ats):
    """Filter + shape jobs into listings rows, deduped within the batch by
    canonical_url (PostgREST upsert can't touch the same conflict row twice)."""
    rows = {}
    for job in jobs:
        canon, title = job.get("canonical_url"), job.get("title")
        if not canon or not title:
            continue
        passed, kws = evaluate(title, job.get("description", ""), job.get("employment_type", ""))
        if not passed:
            continue
        rows[canon] = {
            "canonical_url": canon,
            "raw_url": job.get("raw_url"),
            "title": title,
            "company_slug": slug,
            "ats_source": ats,
            "keywords_matched": kws,
            "snippet": (job.get("description") or "")[:500] or None,
            "posted_at": job.get("posted_at"),
            "last_seen_at": now_iso(),
            # first_seen_at intentionally omitted: default fills it on insert,
            # and the upsert leaves it untouched on conflict (freshness clock).
        }
    return list(rows.values())


def refresh_company(slug, ats, session):
    jobs = fetch_jobs(slug, ats, session)
    rows = _build_rows(jobs, slug, ats)
    if rows:
        db.upsert("listings", rows, on_conflict="canonical_url")
    return len(jobs), len(rows)


def _mark(slug, ats, values):
    db.patch("companies", {"company_slug": f"eq.{slug}", "ats_source": f"eq.{ats}"}, values)


def run_refresh(delay=0.5):
    companies = db.select_all("companies", {"select": "company_slug,ats_source,still_active"})
    session = requests.Session()
    total_seen = total_matched = 0

    for c in companies:
        if c.get("still_active") is False:
            continue
        slug, ats = c["company_slug"], c["ats_source"]
        if ats not in ADAPTERS:
            print(f"  skip {ats}/{slug}: no adapter yet")
            continue
        try:
            seen, matched = refresh_company(slug, ats, session)
            print(f"  {ats}/{slug}: {seen} jobs -> {matched} matched")
            total_seen += seen
            total_matched += matched
            _mark(slug, ats, {"last_polled_at": now_iso()})
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            print(f"  {ats}/{slug}: HTTP {code} — log-and-continue")
            if code == 404:
                _mark(slug, ats, {"still_active": False})
        except Exception as e:  # noqa: BLE001 — never let one company kill the run
            print(f"  {ats}/{slug}: {type(e).__name__}: {e} — log-and-continue")
        time.sleep(delay)

    print(f"TOTAL: {total_seen} jobs seen, {total_matched} matched/upserted")
    return total_seen, total_matched


if __name__ == "__main__":
    run_refresh()

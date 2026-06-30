"""Refresh (Component B): poll each company's ATS public JSON, filter to student
tech roles, upsert into listings. Runs 2x/day in production.

Concurrency — a work-conserving, host-aware scheduler (no worker blocks for long):
  * SHARED-host companies (path-based ATSs: greenhouse/lever/ashby/smartrecruiters/
    workable/rippling — every company of one ATS hits ONE API host) are capped at
    PER_HOST_CAP in flight per host and dispatched round-robin. Calibration showed
    these hosts tolerate >=24 concurrent with 0% 429, so 12 is polite AND fast.
  * UNIQUE-host companies (subdomain ATSs: breezy/recruitee/teamtailor — each
    company is its own host) flow through a free queue any idle worker drains.
  * A worker only waits when EVERY shared host is at its cap AND the free queue is
    empty, so freed workers immediately grab whatever's runnable — the design
    auto-adapts if the host mix shifts (no static pool sizes to retune).
  * Circuit breaker: a shared host that returns TRIP_AFTER consecutive failures
    (e.g. an IP-level 429 block like workable hit locally) is tripped and its
    remaining companies skipped for the run, so one bad host can't drag the job.

All Supabase writes are batched on the main thread after polling.
"""
import threading
import time
from collections import deque
from urllib.parse import urlsplit

import requests

from . import db
from .ats.adapters import ADAPTERS
from .ats.registry import ATS
from .filters import evaluate
from .util import now_iso

_UA = {"User-Agent": "job-bot/0.1 (+https://github.com/Akhatri98/Job-Bot)",
       "Accept": "application/json"}
_local = threading.local()

PER_HOST_CAP = 12   # in-flight per shared host (calibrated: hosts tolerate >=24, 0% 429)
TRIP_AFTER = 8      # consecutive shared-host failures -> skip its remaining this run


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
    return s


def _request(url, session, method="GET", body=None):
    """Two-try fast-fail retry. Host-level concurrency is the scheduler's job now.
    - conn/timeout / 429 / 5xx: one quick retry then give up — dead hosts and
      persistent blocks don't burn long backoff cycles; transient issues clear on
      the retry.
    - 404 / other 4xx: raise immediately (caller retires the board)."""
    last = None
    for i in range(2):
        try:
            if method == "POST":
                r = session.post(url, headers={**_UA, "Content-Type": "application/json"},
                                 json=body or {}, timeout=12)
            else:
                r = session.get(url, headers=_UA, timeout=12)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            if i == 0:
                time.sleep(0.3)
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = requests.HTTPError(f"{r.status_code}", response=r)
            if i == 0:
                time.sleep(0.5)
            continue
        r.raise_for_status()
        return r
    raise last


def fetch_jobs(slug, ats, session):
    cfg = ATS[ats]
    r = _request(cfg["api"].format(slug=slug), session, method=cfg.get("method", "GET"))
    data = r.json() if r.text else {}
    return ADAPTERS[ats](data, slug)


def _build_rows(jobs, slug, ats):
    """Filter + shape jobs into listings rows, deduped within the batch by canonical_url."""
    rows = {}
    for job in jobs:
        canon, title = job.get("canonical_url"), job.get("title")
        if not canon or not title:
            continue
        passed, kws = evaluate(title, job.get("description", ""), job.get("employment_type", ""))
        if not passed:
            continue
        rows[canon] = {
            "canonical_url": canon, "raw_url": job.get("raw_url"), "title": title,
            "company_slug": slug, "ats_source": ats, "keywords_matched": kws,
            "snippet": (job.get("description") or "")[:500] or None,
            "posted_at": job.get("posted_at"), "last_seen_at": now_iso(),
            # first_seen_at omitted: default on insert, untouched on conflict.
        }
    return list(rows.values())


def _poll(slug, ats):
    """Worker unit: fetch + filter one company. No DB writes."""
    try:
        jobs = fetch_jobs(slug, ats, _session())
        return {"slug": slug, "ats": ats, "status": "ok",
                "rows": _build_rows(jobs, slug, ats), "seen": len(jobs)}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else None
        return {"slug": slug, "ats": ats,
                "status": "dead404" if code == 404 else "error", "rows": [], "seen": 0}
    except Exception:  # noqa: BLE001 — never let one company kill the run
        return {"slug": slug, "ats": ats, "status": "error", "rows": [], "seen": 0}


def _chunked_upsert(table, rows, on_conflict, size=500):
    for i in range(0, len(rows), size):
        db.upsert(table, rows[i:i + size], on_conflict=on_conflict)


def run_refresh(workers=60, per_host=PER_HOST_CAP, trip_after=TRIP_AFTER):
    companies = db.select_all("companies", {"select": "company_slug,ats_source,still_active"})

    capped, free = {}, deque()
    for c in companies:
        if c.get("still_active") is False or c["ats_source"] not in ADAPTERS:
            continue
        slug, ats = c["company_slug"], c["ats_source"]
        if ATS[ats]["slug_in"] == "path":            # shared fixed API host -> cap it
            host = urlsplit(ATS[ats]["api"]).netloc
            capped.setdefault(host, deque()).append((slug, ats))
        else:                                         # unique subdomain host -> free queue
            free.append((slug, ats))

    hosts = list(capped.keys())
    n_capped = sum(len(d) for d in capped.values())
    inflight = {h: 0 for h in hosts}
    fails = {h: 0 for h in hosts}
    tripped = set()
    print(f"{len(companies)} companies, {n_capped + len(free)} pollable: "
          f"{n_capped} on {len(hosts)} shared hosts (cap {per_host}), {len(free)} unique-host. "
          f"workers={workers}")

    cond = threading.Condition()
    results = []
    rr = [0]
    skipped_tripped = [0]

    def _next():  # called holding cond; returns (slug, ats, host|None) | "WAIT" | "DONE"
        n = len(hosts)
        for k in range(n):
            idx = (rr[0] + k) % n
            h = hosts[idx]
            if h in tripped:
                continue
            dq = capped[h]
            if dq and inflight[h] < per_host:
                rr[0] = (idx + 1) % n
                slug, ats = dq.popleft()
                inflight[h] += 1
                return slug, ats, h
        if free:
            slug, ats = free.popleft()
            return slug, ats, None
        if any(capped[h] and h not in tripped for h in hosts):
            return "WAIT"   # pending exists but all at cap -> a completion will free a slot
        return "DONE"

    def worker():
        while True:
            with cond:
                while True:
                    t = _next()
                    if t == "DONE":
                        return
                    if t == "WAIT":
                        cond.wait()
                        continue
                    break
                slug, ats, host = t
            res = _poll(slug, ats)
            with cond:
                if host is not None:
                    inflight[host] -= 1
                    if res["status"] == "error":     # 429/conn/5xx — count toward trip
                        fails[host] += 1
                        if fails[host] >= trip_after and host not in tripped:
                            tripped.add(host)
                            skipped_tripped[0] += len(capped[host])
                            capped[host].clear()
                    else:                             # ok / dead404 -> host is healthy
                        fails[host] = 0
                results.append(res)
                if len(results) % 2000 == 0:
                    print(f"  ...{len(results)} polled, {sum(1 for r in results if r['rows'])} matched")
                cond.notify_all()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # ---- aggregate + batched writes (main thread) ----
    all_rows, polled_ok, dead = {}, [], []
    seen = 0
    for res in results:
        if res["status"] == "ok":
            polled_ok.append((res["slug"], res["ats"]))
            seen += res["seen"]
            for row in res["rows"]:
                all_rows[row["canonical_url"]] = row
        elif res["status"] == "dead404":
            dead.append((res["slug"], res["ats"]))

    rows = list(all_rows.values())
    if rows:
        _chunked_upsert("listings", rows, "canonical_url")
    if polled_ok:
        stamp = now_iso()
        _chunked_upsert("companies", [{"company_slug": s, "ats_source": a, "last_polled_at": stamp}
                                      for s, a in polled_ok], "company_slug,ats_source")
    if dead:
        _chunked_upsert("companies", [{"company_slug": s, "ats_source": a, "still_active": False}
                                      for s, a in dead], "company_slug,ats_source")

    errs = sum(1 for r in results if r["status"] == "error")
    print(f"TOTAL: {seen} jobs seen, {len(rows)} listings upserted, {len(dead)} retired (404), "
          f"{errs} errors, {len(tripped)} hosts tripped ({skipped_tripped[0]} skipped)")
    return seen, len(rows)


if __name__ == "__main__":
    run_refresh()

"""Refresh (Component B): poll each company's ATS public JSON, filter to student
tech roles, upsert into listings.

Two profiles share one engine (see Policy):
  * FAST  — runs 2x/day. Speed-first: small retry budget, low circuit-breaker
            threshold, batch-write at the end. Finishes in minutes.
  * DEEP  — runs nightly with hours of leeway. Completeness-first: patient retries,
            high trip threshold (still gives up on a truly-dead host so it can't
            grind for hours), and incremental flushing so a long run survives a
            crash. Reclaims the per-run completeness/durability that FAST trades away.

Concurrency — a work-conserving, host-aware scheduler (no worker blocks for long):
  * SHARED-host companies (path-based ATSs: greenhouse/lever/ashby/smartrecruiters/
    workable/rippling — every company of one ATS hits ONE API host) are capped at
    Policy.per_host in flight per host and dispatched round-robin (calibration: these
    hosts tolerate >=24 concurrent with 0% 429).
  * UNIQUE-host companies (subdomain ATSs: breezy/recruitee/teamtailor — each company
    is its own host) flow through a free queue any idle worker drains.
  * A worker only waits when EVERY shared host is at cap AND the free queue is empty.
  * Circuit breaker: a shared host with Policy.trip_after consecutive failures is
    tripped and its remaining companies skipped for the run.
"""
import threading
import time
from collections import deque
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Policy:
    workers: int = 60
    per_host: int = 12          # in-flight per shared host
    attempts: int = 2           # tries per request (conn/timeout/429/5xx)
    timeout: int = 12           # per-request seconds
    backoff: float = 0.5        # base backoff for 429/5xx
    conn_backoff: float = 0.3   # base backoff for connection/timeout
    trip_after: int = 8         # consecutive shared-host failures -> trip (skip rest)
    flush_interval: float = 0   # >0 -> flush to DB every N seconds; 0 -> batch at end


FAST = Policy()
DEEP = Policy(workers=40, per_host=10, attempts=5, timeout=25, backoff=1.0,
              conn_backoff=0.5, trip_after=100, flush_interval=30)

# A board that persistently FAILS — unreachable (DNS/conn/timeout) or HTTP 410 Gone,
# the unambiguous "this board is dead" signals — this many polls in a row gets
# retired (still_active=false). Deliberately excludes 429/5xx (transient) and
# 403/401 (ambiguous IP/UA blocks). ~3 runs/day, so ~3 days; any success resets the
# count, so a maintenance blip won't reap a live board.
RETIRE_AFTER = 10


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
    return s


def _request(url, session, policy, method="GET", body=None):
    """Retry per policy. Host-level concurrency is the scheduler's job.
    conn/timeout/429/5xx are retried (with backoff) up to policy.attempts; 404 and
    other 4xx raise immediately (caller retires the board)."""
    last = None
    for i in range(policy.attempts):
        last_attempt = i == policy.attempts - 1
        try:
            if method == "POST":
                r = session.post(url, headers={**_UA, "Content-Type": "application/json"},
                                 json=body or {}, timeout=policy.timeout)
            else:
                r = session.get(url, headers=_UA, timeout=policy.timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = e
            if not last_attempt:
                time.sleep(policy.conn_backoff * (2 ** i))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            last = requests.HTTPError(f"{r.status_code}", response=r)
            if not last_attempt:
                time.sleep(policy.backoff * (2 ** i))
            continue
        r.raise_for_status()
        return r
    raise last


def fetch_jobs(slug, ats, session, policy=FAST):
    cfg = ATS[ats]
    r = _request(cfg["api"].format(slug=slug), session, policy, method=cfg.get("method", "GET"))
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
        }
    return list(rows.values())


def _poll(slug, ats, policy):
    try:
        jobs = fetch_jobs(slug, ats, _session(), policy)
        return {"slug": slug, "ats": ats, "status": "ok",
                "rows": _build_rows(jobs, slug, ats), "seen": len(jobs)}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        if code == 404:
            return {"slug": slug, "ats": ats, "status": "dead404", "rows": [], "seen": 0}
        if code == 410:  # Gone — board definitively removed -> counts toward retire
            return {"slug": slug, "ats": ats, "status": "pfail", "rows": [], "seen": 0}
        # 429/5xx (transient) and 403/401 (ambiguous IP/UA block) -> retry next run
        return {"slug": slug, "ats": ats, "status": "error", "rows": [], "seen": 0}
    except (requests.ConnectionError, requests.Timeout):
        # won't resolve / refuses / hangs -> persistent failure, counts toward retire
        return {"slug": slug, "ats": ats, "status": "pfail", "rows": [], "seen": 0}
    except Exception:  # noqa: BLE001 — never let one company kill the run
        return {"slug": slug, "ats": ats, "status": "error", "rows": [], "seen": 0}


def _chunked_upsert(table, rows, on_conflict, size=500):
    for i in range(0, len(rows), size):
        db.upsert(table, rows[i:i + size], on_conflict=on_conflict)


def _write(batch, fail_map):
    """Persist a batch: listings + last_polled_at + retirements. A success resets
    fail_count to 0; an UNREACHABLE poll bumps it, and a board retires once it hits
    RETIRE_AFTER consecutive. 404 retires immediately; 429/5xx are left untouched."""
    all_rows, polled_ok, retire, bump = {}, [], [], []
    for res in batch:
        pair = (res["slug"], res["ats"])
        st = res["status"]
        if st == "ok":
            polled_ok.append(pair)
            for row in res["rows"]:
                all_rows[row["canonical_url"]] = row
        elif st == "dead404":
            retire.append(pair)
        elif st == "pfail":
            n = fail_map.get(pair, 0) + 1
            if n >= RETIRE_AFTER:
                retire.append(pair)
            else:
                bump.append((pair, n))
        # "error" (429/5xx) -> transient/blocked, leave the row untouched

    if all_rows:
        _chunked_upsert("listings", list(all_rows.values()), "canonical_url")
    if polled_ok:
        stamp = now_iso()
        _chunked_upsert("companies", [{"company_slug": s, "ats_source": a,
                                       "last_polled_at": stamp, "fail_count": 0}
                                      for s, a in polled_ok], "company_slug,ats_source")
    if retire:
        _chunked_upsert("companies", [{"company_slug": s, "ats_source": a, "still_active": False}
                                      for s, a in retire], "company_slug,ats_source")
    if bump:
        _chunked_upsert("companies", [{"company_slug": s, "ats_source": a, "fail_count": n}
                                      for (s, a), n in bump], "company_slug,ats_source")
    return sum(len(r["rows"]) for r in batch if r["status"] == "ok")


def run_refresh(policy=FAST, workers=None):
    workers = workers or policy.workers
    companies = db.select_all("companies",
                              {"select": "company_slug,ats_source,still_active,fail_count"})
    fail_map = {(c["company_slug"], c["ats_source"]): c.get("fail_count") or 0 for c in companies}

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
          f"{n_capped} on {len(hosts)} shared hosts (cap {policy.per_host}), {len(free)} unique-host. "
          f"workers={workers}, attempts={policy.attempts}, trip@{policy.trip_after}, "
          f"flush={policy.flush_interval or 'end'}")

    cond = threading.Condition()
    results = []
    rr = [0]
    skipped_tripped = [0]

    def _next():  # holding cond; returns (slug, ats, host|None) | "WAIT" | "DONE"
        n = len(hosts)
        for k in range(n):
            idx = (rr[0] + k) % n
            h = hosts[idx]
            if h in tripped:
                continue
            dq = capped[h]
            if dq and inflight[h] < policy.per_host:
                rr[0] = (idx + 1) % n
                slug, ats = dq.popleft()
                inflight[h] += 1
                return slug, ats, h
        if free:
            slug, ats = free.popleft()
            return slug, ats, None
        if any(capped[h] and h not in tripped for h in hosts):
            return "WAIT"
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
            res = _poll(slug, ats, policy)
            with cond:
                if host is not None:
                    inflight[host] -= 1
                    if res["status"] in ("error", "pfail"):
                        fails[host] += 1
                        if fails[host] >= policy.trip_after and host not in tripped:
                            tripped.add(host)
                            skipped_tripped[0] += len(capped[host])
                            capped[host].clear()
                    else:
                        fails[host] = 0
                results.append(res)
                if len(results) % 2000 == 0:
                    print(f"  ...{len(results)} polled, {sum(1 for r in results if r['rows'])} matched")
                cond.notify_all()

    # optional incremental flusher (DEEP) — single thread owns DB writes, so the
    # shared db session is never touched concurrently.
    flushed = [0]
    stop_flush = threading.Event()

    def _flush():
        with cond:
            batch, flushed[0] = results[flushed[0]:], len(results)
        if batch:
            _write(batch, fail_map)

    def flusher():
        while not stop_flush.wait(policy.flush_interval):
            _flush()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    fl = threading.Thread(target=flusher, daemon=True) if policy.flush_interval else None
    for t in threads:
        t.start()
    if fl:
        fl.start()
    for t in threads:
        t.join()
    if fl:
        stop_flush.set()
        fl.join()

    _flush()  # final flush (the whole run, for FAST; the remainder, for DEEP)

    seen = sum(r["seen"] for r in results if r["status"] == "ok")
    upserted = len({row["canonical_url"] for r in results if r["status"] == "ok" for row in r["rows"]})
    pfail = sum(1 for r in results if r["status"] == "pfail")
    retired = sum(1 for r in results if r["status"] == "dead404") + sum(
        1 for r in results if r["status"] == "pfail"
        and fail_map.get((r["slug"], r["ats"]), 0) + 1 >= RETIRE_AFTER)
    errs = sum(1 for r in results if r["status"] == "error")
    print(f"TOTAL: {seen} jobs seen, {upserted} listings, {retired} retired, "
          f"{pfail} persistent-fail, {errs} errors, {len(tripped)} hosts tripped "
          f"({skipped_tripped[0]} skipped)")
    return seen, upserted


if __name__ == "__main__":
    run_refresh()

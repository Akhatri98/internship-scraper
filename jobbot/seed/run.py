"""Seed orchestrator (Stage 3, one-time).

Capture-raw-FIRST: every Serper response is written to JSONL before we parse it,
so a slug-parser bug never forces re-spending the non-recurring grant. A
flattened CSV is the convenient parsed view. Confident (slug, ats) pairs are
upserted into companies (pair-level dedup).

Free Serper = 10 results/request, 1 credit each, no `num` override. To buy the
most UNIQUE companies per credit we go BREADTH-FIRST round-robin: page 1 to every
(domain, field) combo, then page 2 to combos whose previous page was full, etc.
Deep pages of a site: query mostly repeat the same big companies, so width beats
depth for slug yield. A hard credit budget protects the grant.

Use via scripts/seed_run.py (preview / --dry-run / --go).
"""
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .. import db
from ..serper import search
from .domains import extract
from .queryplan import DRYRUN_SAMPLE, build_queries

_OUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "seed"
_CSV_COLS = ["query", "field", "page", "position", "url", "ats", "slug", "title"]
_FULL_PAGE = 10  # free plan returns 10 results when more exist


def preview(domains=None, fields=None):
    queries = build_queries(domains, fields)
    bare = sum(1 for q in queries if q["field"] == "")
    print(f"Query plan: {len(queries)} base combos "
          f"({bare} bare site sweeps + {len(queries) - bare} field-sliced)")
    print(f"  domains: {len({q['domain'] for q in queries})}, "
          f"fields: {len({q['field'] for q in queries if q['field']})}")
    print("  Free Serper: 10 results/request, 1 credit each. Breadth-first round-robin,")
    print("  hard-capped by --budget credits (default 2400, leaving grant headroom).")
    print("\nNO API CALLS MADE. Run --dry-run to validate, then --go to burn.")
    return queries


def run_seed(*, queries, max_pages, budget, label, do_upsert=True, delay=0.3):
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = _OUT_DIR / f"{label}_{stamp}.jsonl"
    csv_path = _OUT_DIR / f"{label}_{stamp}.csv"

    session = requests.Session()
    credits = 0
    raw_rows = 0
    seen_pairs = set()
    pairs = []
    upserted = 0
    alive = [True] * len(queries)

    def flush():
        nonlocal upserted
        if not do_upsert:
            return
        new = pairs[upserted:]
        for j in range(0, len(new), 500):
            db.upsert("companies", new[j:j + 500], on_conflict="company_slug,ats_source")
        upserted += len(new)

    budget_txt = budget if budget is not None else "unlimited"
    print(f"{len(queries)} combos, max_pages={max_pages}, budget={budget_txt} credits.")
    print(f"raw -> {jsonl_path.name}, csv -> {csv_path.name}\n")

    stopped = False
    with open(jsonl_path, "w", encoding="utf-8") as jf, \
         open(csv_path, "w", encoding="utf-8", newline="") as cf:
        writer = csv.writer(cf)
        writer.writerow(_CSV_COLS)

        for page in range(1, max_pages + 1):
            if stopped or not any(alive):
                break
            for i, spec in enumerate(queries):
                if not alive[i]:
                    continue
                if budget is not None and credits >= budget:
                    print(f"\nBudget reached ({credits} credits) — stopping.")
                    stopped = True
                    break
                try:
                    resp = search(spec["q"], page=page, session=session)
                except requests.HTTPError as e:
                    code = e.response.status_code if e.response is not None else "?"
                    if code in (401, 403, 429):  # bad key / out of credits — abort
                        print(f"  {spec['q']!r} p{page}: HTTP {code} — ABORT")
                        raise
                    alive[i] = False
                    continue

                # ---- CAPTURE RAW FIRST (before any parsing) ----
                jf.write(json.dumps({"q": spec["q"], "domain": spec["domain"],
                                     "ats": spec["ats"], "field": spec["field"],
                                     "page": page, "response": resp}) + "\n")
                jf.flush()

                credits += resp.get("credits", 1) or 1
                organic = resp.get("organic", []) or []
                for item in organic:
                    url = item.get("link") or ""
                    parsed = extract(url)
                    ats, slug = parsed if parsed else (spec["ats"], "")
                    writer.writerow([spec["q"], spec["field"], page, item.get("position"),
                                     url, ats, slug, (item.get("title") or "")[:200]])
                    raw_rows += 1
                    if slug and (slug, ats) not in seen_pairs:
                        seen_pairs.add((slug, ats))
                        pairs.append({"company_slug": slug, "ats_source": ats})

                if len(organic) < _FULL_PAGE:
                    alive[i] = False  # exhausted, don't request further pages
                time.sleep(delay)

            flush()  # incremental upsert per page-wave -> crash-resilient population
            print(f"  page {page} done: {credits} credits, {len(seen_pairs)} unique pairs "
                  f"({upserted} upserted), {sum(alive)} combos still alive")

    flush()  # catch anything from the final wave
    print(f"\nCaptured {raw_rows} result rows, {len(seen_pairs)} unique (slug, ats) pairs.")
    print(f"Credits used this run: {credits}")
    if do_upsert:
        print(f"Upserted {upserted} pairs into companies (pair-level dedup).")

    return {"queries": len(queries), "credits": credits, "rows": raw_rows,
            "unique_pairs": len(seen_pairs), "upserted": upserted,
            "jsonl": str(jsonl_path), "csv": str(csv_path)}


def dry_run():
    print("=== DRY RUN: diverse combos (path + subdomain + messy long-tail), 2 pages ===\n")
    return run_seed(queries=DRYRUN_SAMPLE, max_pages=2, budget=None, label="dryrun")


def full_burn(max_pages=10, budget=2400, max_queries=None):
    queries = build_queries()
    if max_queries:
        queries = queries[:max_queries]
    print(f"=== FULL BURN: {len(queries)} combos ===\n")
    return run_seed(queries=queries, max_pages=max_pages, budget=budget, label="seed", delay=0.2)

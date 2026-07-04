"""One-off repair: make Workday companies pollable.

Workday rows were seeded with a bare tenant slug ("blueorigin"), but polling the
CXS API needs the full "tenant.wdN/Site" composite (datacenter host + career-site
name). The seed capture (data/seed/*.jsonl|csv) preserved the original URLs, so
we can rebuild composites for every tenant that came from the seed. Plan:

  1. Scan seed files for myworkdayjobs.com URLs -> composite slugs via
     seed.domains.extract (which now emits composites for workday).
  2. Live-verify each candidate with one CXS request (a tenant can host several
     career sites — keep every one that answers 200).
  3. Upsert verified composites as new companies rows.
  4. Retire (still_active=false) every bare-slug workday row — with or without a
     mapping they are unpollable; tenants that only ever came from Common Crawl
     discovery get re-added as composites on the next discovery run.

  python -m scripts.repair_workday            # do it
  python -m scripts.repair_workday --dry-run  # report only, no DB writes
"""
import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from jobbot import db
from jobbot.seed.domains import extract

_SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"
_WD_URL = re.compile(r'https://[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[^\s"\\,]*')
_UA = {"User-Agent": "job-bot/0.1 (+https://github.com/Akhatri98/Job-Bot)",
       "Accept": "application/json"}


def harvest_composites() -> set[str]:
    """Every distinct workday composite slug found in the seed capture."""
    composites = set()
    for f in _SEED_DIR.glob("seed_*.*"):
        text = f.read_text(encoding="utf-8", errors="replace")
        for url in _WD_URL.findall(text):
            parsed = extract(url)
            if parsed and parsed[0] == "workday":
                composites.add(parsed[1])
    return composites


def verify(composite: str, session: requests.Session) -> bool:
    """True iff the CXS endpoint answers 200 for this tenant/host/site."""
    hostpart, _, site = composite.partition("/")
    tenant = hostpart.split(".")[0]
    url = f"https://{hostpart}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    for _ in range(2):  # one retry for transient 5xx
        try:
            r = session.post(url, json={"limit": 1, "offset": 0, "searchText": ""},
                             headers={**_UA, "Content-Type": "application/json"}, timeout=15)
        except (requests.ConnectionError, requests.Timeout):
            continue
        if r.status_code == 200:
            return True
        if r.status_code < 500:
            return False
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="report only, no DB writes")
    args = ap.parse_args()

    candidates = sorted(harvest_composites())
    print(f"{len(candidates)} composite candidates in seed capture")

    session = requests.Session()
    with ThreadPoolExecutor(max_workers=16) as ex:
        oks = list(ex.map(lambda c: verify(c, session), candidates))
    verified = [c for c, ok in zip(candidates, oks) if ok]
    dead = [c for c, ok in zip(candidates, oks) if not ok]
    print(f"{len(verified)} verified live, {len(dead)} dead/unreachable")
    if dead[:10]:
        print("  dead sample:", dead[:10])

    rows = db.select_all("companies", {"select": "company_slug,ats_source,still_active",
                                       "ats_source": "eq.workday"})
    bare = [r["company_slug"] for r in rows if "/" not in r["company_slug"]]
    have = {r["company_slug"] for r in rows}
    new = [c for c in verified if c not in have]
    covered_tenants = {c.split(".")[0] for c in verified}
    orphans = [s for s in bare if s not in covered_tenants]
    print(f"{len(rows)} workday rows in db: {len(bare)} bare (unpollable), "
          f"{len(new)} composites to add, {len(orphans)} tenants with no seed mapping "
          f"(await next discovery run)")

    if args.dry_run:
        print("dry-run: no writes")
        return

    for i in range(0, len(new), 500):
        db.upsert("companies", [{"company_slug": c, "ats_source": "workday"}
                                for c in new[i:i + 500]],
                  on_conflict="company_slug,ats_source")
    print(f"added {len(new)} composite rows")

    for i in range(0, len(bare), 500):
        db.upsert("companies", [{"company_slug": s, "ats_source": "workday",
                                 "still_active": False}
                                for s in bare[i:i + 500]],
                  on_conflict="company_slug,ats_source")
    print(f"retired {len(bare)} bare-slug rows")


if __name__ == "__main__":
    main()

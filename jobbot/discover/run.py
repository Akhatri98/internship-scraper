import requests
from .. import db
from ..seed.domains import SEED_DOMAINS, extract
from .commoncrawl import IndexUnavailable, iter_urls, latest_index


def _pattern(domain: str, slug_in: str) -> str:
    return f"{domain}/*" if slug_in == "path" else f"*.{domain}"


def run_discover(*, domains=None, index=None, max_pages=None, do_upsert=True):
    index = index or latest_index()
    domains = domains or SEED_DOMAINS
    print(f"Discover against {index}\n")

    existing = {(c["company_slug"], c["ats_source"])
                for c in db.select_all("companies", {"select": "company_slug,ats_source"})}
    print(f"{len(existing)} companies already in db.\n")

    session = requests.Session()
    seen = set()
    total_new = 0
    failed = []

    for domain, ats, slug_in in domains:
        pattern = _pattern(domain, slug_in)
        batch = []
        err = None
        try:
            for url in iter_urls(pattern, index, max_pages=max_pages, session=session):
                parsed = extract(url)
                if not parsed:
                    continue
                ats_x, slug_x = parsed  # extract() returns (ats, slug)
                key = (slug_x, ats_x)   # match the (company_slug, ats_source) ordering
                if key in existing or key in seen:
                    continue
                seen.add(key)
                batch.append({"company_slug": slug_x, "ats_source": ats_x})
        except IndexUnavailable as e:
            err = e  # keep going: other domains may still read, and this batch is still real
            failed.append(str(e))

        # Upsert even a partial batch — discovery only appends, so what we did
        # read is valid, and a rerun skips it via `existing`.
        if do_upsert and batch:
            for j in range(0, len(batch), 500):
                db.upsert("companies", batch[j:j + 500], on_conflict="company_slug,ats_source")
        total_new += len(batch)
        print(f"  {pattern}: +{len(batch)} new" + (f"  [INCOMPLETE: {err}]" if err else ""))

    print(f"\nTotal new companies discovered: {total_new}")
    if failed:
        # Fail the run (red in Actions). Without this an index outage reads as
        # "+0 new" on every domain and a green check — indistinguishable from a
        # genuinely quiet month.
        raise SystemExit(
            f"FAIL: Common Crawl index unreadable for {len(failed)}/{len(domains)} domain(s) "
            f"- this run is INCOMPLETE, not a quiet month:\n  " + "\n  ".join(failed) +
            "\nWhatever was read has been saved; rerun once the index recovers "
            "(discovery only appends, so a rerun is safe).")
    return total_new

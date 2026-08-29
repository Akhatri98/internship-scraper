"""One-off repair: collapse case-variant Workday duplicates.

jobbot/seed/domains.py used to preserve the case of a Workday career-site segment
("tenant.wdN/CVS_Health_Careers") while every other ATS lowercased its slug. The
CXS API is case-insensitive, so a tenant discovered from two differently-cased
URLs became TWO companies rows for one real board — each polling OK, each minting
its own canonical_url, producing two parallel copies of every listing. At the time
of writing that was 334 duplicate board pairs and ~8.4k twin listing rows (23% of
the table), and the copies rotted into prune's "gone" bucket.

domains.py now lowercases, so no NEW duplicates appear. This cleans up the ones
already in the database:

  * companies — keep the lowercase row per (lower(slug), ats), merging the best
    of the group: newest last_polled_at / last_full_poll_at, lowest fail_count,
    still_active True if any variant is live. Delete the other rows.
  * listings  — within each lower(canonical_url) group keep ONE row, preserving
    history (oldest first_seen_at, newest last_seen_at), rewrite its site segment
    to lowercase, and delete the rest.

  python -m scripts.dedupe_workday             # dry run, writes nothing
  python -m scripts.dedupe_workday --apply     # do it

Run this BEFORE creating the case-insensitive unique index on companies — the
index cannot be built while duplicates are still present.
"""
import argparse
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

from jobbot import db

_CHUNK = 100  # ids per `in.(...)` delete, keeps the URL well under limits


def _canon_slug(slug: str) -> str:
    """The surviving identity for a workday composite: fully lowercased."""
    return (slug or "").lower()


def _canon_url(url: str) -> str:
    """Lowercase ONLY the career-site path segment of a Workday listing URL.

    /en-US/CVS_Health_Careers/job/NE---Kearney/Pharmacy-Intern_R123
           ^^^^^^^^^^^^^^^^^^ this one; the locale and the job path (which comes
    verbatim from the CXS externalPath) keep their case.
    """
    parts = urlsplit(url or "")
    segs = parts.path.split("/")
    # ["", "en-US", "<site>", "job", ...] — site is index 2 when a locale leads.
    if len(segs) > 2 and segs[1]:
        segs[2] = segs[2].lower()
    return urlunsplit((parts.scheme, parts.netloc.lower(), "/".join(segs),
                       parts.query, parts.fragment))


def _newest(rows, field):
    vals = [r.get(field) for r in rows if r.get(field)]
    return max(vals) if vals else None


def _merge_company(group):
    """One winning companies row from a case-variant group."""
    slug = _canon_slug(group[0]["company_slug"])
    fails = [r.get("fail_count") for r in group if r.get("fail_count") is not None]
    return {
        "company_slug": slug,
        "ats_source": group[0]["ats_source"],
        "last_polled_at": _newest(group, "last_polled_at"),
        "last_full_poll_at": _newest(group, "last_full_poll_at"),
        # A board live under ANY casing is live; only retire when every variant is.
        "still_active": any(r.get("still_active") is not False for r in group),
        "fail_count": min(fails) if fails else 0,
    }


def _pick_listing(group):
    """Keep the row carrying the longest history for this job."""
    keep = max(group, key=lambda r: (r.get("last_seen_at") or ""))
    first = min((r.get("first_seen_at") for r in group if r.get("first_seen_at")), default=None)
    return keep, first


def _delete_ids(table, ids, apply):
    if not apply:
        return
    for i in range(0, len(ids), _CHUNK):
        db.delete(table, {"id": f"in.({','.join(ids[i:i + _CHUNK])})"})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="actually write; without it this is a dry run")
    args = ap.parse_args()
    apply = args.apply
    print("APPLYING CHANGES" if apply else "DRY RUN — no writes\n")

    # ---------------- companies ----------------
    companies = db.select_all("companies", {
        "select": "company_slug,ats_source,last_polled_at,last_full_poll_at,"
                  "still_active,fail_count",
        "ats_source": "eq.workday"})
    groups = defaultdict(list)
    for c in companies:
        groups[(_canon_slug(c["company_slug"]), c["ats_source"])].append(c)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}
    losers = [c for v in dupes.values() for c in v
              if c["company_slug"] != _canon_slug(c["company_slug"])]
    print(f"companies: {len(companies)} workday rows, {len(dupes)} case-variant groups, "
          f"{len(losers)} rows to remove")
    for k, v in list(dupes.items())[:5]:
        print(f"    {k[0][:52]:<52} <- {', '.join(sorted(c['company_slug'] for c in v))}")

    if dupes:
        merged = [_merge_company(v) for v in dupes.values()]
        if apply:
            for i in range(0, len(merged), 500):
                db.upsert("companies", merged[i:i + 500], on_conflict="company_slug,ats_source")
        print(f"  {'upserted' if apply else 'would upsert'} {len(merged)} merged rows")

    # ---------------- listings ----------------
    listings = db.select_all("listings", {
        "select": "id,canonical_url,raw_url,company_slug,ats_source,"
                  "first_seen_at,last_seen_at",
        "ats_source": "eq.workday"})
    byurl = defaultdict(list)
    for l in listings:
        byurl[_canon_url(l["canonical_url"])].append(l)

    drop_ids, rewrites = [], []
    for canon, group in byurl.items():
        keep, first = _pick_listing(group)
        drop_ids += [r["id"] for r in group if r["id"] != keep["id"]]
        need_url = keep["canonical_url"] != canon
        need_slug = keep["company_slug"] != _canon_slug(keep["company_slug"])
        need_first = first and first != keep.get("first_seen_at")
        if need_url or need_slug or need_first:
            # A PATCH writes only what it carries — send just the changed fields.
            row = {}
            if need_url:
                row["canonical_url"] = canon
                row["raw_url"] = _canon_url(keep.get("raw_url") or keep["canonical_url"])
            if need_slug:
                row["company_slug"] = _canon_slug(keep["company_slug"])
            if need_first:
                row["first_seen_at"] = first
            rewrites.append((keep["id"], row))

    dup_rows = sum(len(v) - 1 for v in byurl.values() if len(v) > 1)
    print(f"\nlistings: {len(listings)} workday rows, {len(byurl)} distinct jobs, "
          f"{dup_rows} duplicate rows to remove")
    print(f"  {len(rewrites)} survivors need a canonical rewrite")

    if apply:
        # Losers go FIRST: the survivor often needs to claim a canonical_url that
        # a loser currently holds, and canonical_url is unique — the key has to be
        # free before the rewrite can take it.
        _delete_ids("listings", drop_ids, apply)
        for lid, row in rewrites:
            db.patch("listings", {"id": f"eq.{lid}"}, row)
        # Company rows last — a listing must never be an orphan mid-migration.
        for i in range(0, len(losers), _CHUNK):
            for c in losers[i:i + _CHUNK]:
                db.delete("companies", {"company_slug": f"eq.{c['company_slug']}",
                                        "ats_source": f"eq.{c['ats_source']}"})
        print(f"\ndeleted {len(drop_ids)} listings, rewrote {len(rewrites)}, "
              f"removed {len(losers)} company rows")
    else:
        print(f"\nwould delete {len(drop_ids)} listings, rewrite {len(rewrites)}, "
              f"remove {len(losers)} company rows")
        print("\nrerun with --apply to execute")


if __name__ == "__main__":
    main()

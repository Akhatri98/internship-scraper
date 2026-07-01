"""Prune (Component C): delete listings a healthy board no longer serves.

A filled/closed job silently drops out of its ATS feed. The board still polls
200-OK, so RETIRE_AFTER never fires (that reaps dead BOARDS, not dead JOBS) and
the row lingers forever with a stale last_seen_at. This nightly sweep removes it,
using successful polls as ground truth — no per-URL HTTP checks needed:

  * GONE   — the listing's company was polled OK strictly more recently than the
             job was last seen (by STALE_MARGIN, which absorbs intra-run write
             skew). A fresh successful poll that didn't re-include the job == the
             job is closed.
  * DEAD   — the listing's board is retired (still_active=false): the whole board
             is gone, so every listing on it is dead.
  * ORPHAN — the listing has no matching companies row: unmaintainable, can never
             be re-confirmed by Refresh.

Critically, it NEVER prunes when we lack a newer successful poll — a board that's
currently down keeps its listings until it either recovers or is retired — so an
outage can't wipe live jobs. A safety cap aborts the run if the delete set is
implausibly large (guards against a mass mis-stamp or a logic bug).

Runs AFTER the nightly DEEP refresh (see freshness-prune.yml), so last_polled_at
reflects the most thorough recent sweep before we judge staleness.
"""
from datetime import datetime, timedelta

from . import db

# > the longest plausible FAST run (its timeout is 30m; all rows share one
# end-of-run last_polled_at while last_seen_at spans the run) and < the 4h gap
# between FAST runs, so a still-live job is never mistaken for gone.
STALE_MARGIN = timedelta(hours=2)

# Refuse to delete more than this share of all listings in one run.
SAFETY_FRACTION = 0.40

_DELETE_CHUNK = 100  # UUIDs per `id=in.(...)` delete (keeps the URL well under limits)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _classify(listings, cmap):
    """Split listings into (gone, dead_board, orphan) prune buckets."""
    gone, dead, orphan = [], [], []
    for lst in listings:
        c = cmap.get((lst["company_slug"], lst["ats_source"]))
        if c is None:
            orphan.append(lst)
            continue
        if c.get("still_active") is False:
            dead.append(lst)
            continue
        polled, seen = _parse(c.get("last_polled_at")), _parse(lst.get("last_seen_at"))
        if polled and seen and polled - seen > STALE_MARGIN:
            gone.append(lst)
    return gone, dead, orphan


def run_prune(dry_run=False):
    companies = db.select_all(
        "companies", {"select": "company_slug,ats_source,last_polled_at,still_active"})
    cmap = {(c["company_slug"], c["ats_source"]): c for c in companies}

    listings = db.select_all(
        "listings", {"select": "id,canonical_url,company_slug,ats_source,last_seen_at"})

    gone, dead, orphan = _classify(listings, cmap)
    doomed = gone + dead + orphan
    total = len(listings)
    print(f"{total} listings scanned — prune candidates: "
          f"{len(gone)} gone (closed on a live board), {len(dead)} on dead boards, "
          f"{len(orphan)} orphan -> {len(doomed)} total")

    if total and len(doomed) / total > SAFETY_FRACTION:
        raise SystemExit(
            f"ABORT: would prune {len(doomed)}/{total} ({len(doomed) / total:.0%} "
            f"> {SAFETY_FRACTION:.0%} cap) — refusing. Investigate before rerunning "
            f"(a mass mis-stamp or a stalled poll can trip this).")

    if dry_run:
        print("dry-run: nothing deleted")
        return len(doomed)
    if not doomed:
        print("nothing to prune")
        return 0

    ids = [lst["id"] for lst in doomed]
    for i in range(0, len(ids), _DELETE_CHUNK):
        chunk = ids[i:i + _DELETE_CHUNK]
        db.delete("listings", {"id": f"in.({','.join(chunk)})"})
    print(f"deleted {len(ids)} listings")
    return len(ids)


if __name__ == "__main__":
    run_prune()

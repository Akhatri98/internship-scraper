"""Prune (Component C): delete listings a healthy board no longer serves.

A filled/closed job silently drops out of its ATS feed. The board still polls
200-OK, so RETIRE_AFTER never fires (that reaps dead BOARDS, not dead JOBS) and
the row lingers forever with a stale last_seen_at. This nightly sweep removes it,
using successful polls as ground truth — no per-URL HTTP checks needed:

  * GONE   — the listing's company was COMPLETELY swept strictly more recently
             than the job was last seen (by STALE_MARGIN, which absorbs intra-run
             write skew). A fresh exhaustive poll that didn't re-include the job
             == the job is closed. "Completely" is load-bearing: a truncated poll
             (e.g. a Workday board bigger than the fetcher's page budget) leaves
             live jobs unseen, and judging on one would delete them. So this reads
             last_full_poll_at — stamped only by an exhaustive sweep, see
             refresh._write — and a board never fully swept (NULL) is never judged.
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
from collections import Counter
from datetime import UTC, datetime, timedelta

from . import db

# > the longest plausible FAST run (its timeout is 30m; a listing's last_seen_at
# and its company's last_polled_at are stamped by different flushes within the
# run), so a still-live job is never mistaken for gone. With hourly FAST runs
# this means a job must be absent from ~2 consecutive successful polls to be
# judged closed — margin only delays pruning, so bigger is the safe direction.
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
        # NOT last_polled_at: only an exhaustive sweep proves absence.
        polled, seen = _parse(c.get("last_full_poll_at")), _parse(lst.get("last_seen_at"))
        if polled and seen and polled - seen > STALE_MARGIN:
            gone.append(lst)
    return gone, dead, orphan


def _seen_epoch(lst) -> float:
    """last_seen_at as a sortable float; unparseable/missing sorts oldest-first."""
    d = _parse(lst.get("last_seen_at"))
    if d is None:
        return float("-inf")
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).timestamp()


def _breakdown(label, rows):
    """Per-ATS tally for one bucket, so an abort is diagnosable, not just loud."""
    if not rows:
        return
    by_ats = Counter(r.get("ats_source") for r in rows)
    print(f"  {label} ({len(rows)}): " +
          ", ".join(f"{a}={n}" for a, n in by_ats.most_common()))


def _report(gone, dead, orphan, listings):
    """Why the candidate set looks the way it does — the missing context when the
    safety cap trips (a truncated poll shows up here as one ATS dominating)."""
    print("candidate breakdown:")
    _breakdown("gone (closed on a live board)", gone)
    _breakdown("dead board", dead)
    _breakdown("orphan", orphan)
    tot_by_ats = Counter(l.get("ats_source") for l in listings)
    gone_by_ats = Counter(l.get("ats_source") for l in gone)
    print("  gone share by ats: " + ", ".join(
        f"{a}={gone_by_ats[a]}/{t} ({gone_by_ats[a] / t:.0%})"
        for a, t in tot_by_ats.most_common() if t))
    top = Counter((l.get("company_slug"), l.get("ats_source")) for l in gone).most_common(10)
    if top:
        print("  top companies by gone count:")
        for (slug, ats), n in top:
            print(f"    {str(slug)[:44]:<44} {ats:<16} {n}")


def run_prune(dry_run=False, force=False, max_delete=None):
    """Delete listings a healthy board no longer serves.

    force=True overrides the SAFETY_FRACTION abort. It exists for deliberate
    operator recovery — clearing a backlog that built up while prune was stuck —
    and must never be wired into a workflow: the whole point of the cap is that
    nothing unattended can ever mass-delete. Pair it with max_delete to bound the
    blast radius; the most-stale listings go first.
    """
    companies = db.select_all(
        "companies",
        {"select": "company_slug,ats_source,last_polled_at,last_full_poll_at,still_active"})
    cmap = {(c["company_slug"], c["ats_source"]): c for c in companies}

    listings = db.select_all(
        "listings", {"select": "id,canonical_url,company_slug,ats_source,last_seen_at"})

    gone, dead, orphan = _classify(listings, cmap)
    doomed = gone + dead + orphan
    total = len(listings)
    never_swept = sum(1 for c in companies
                      if c.get("still_active") is not False and not c.get("last_full_poll_at"))
    print(f"{total} listings scanned — prune candidates: "
          f"{len(gone)} gone (closed on a live board), {len(dead)} on dead boards, "
          f"{len(orphan)} orphan -> {len(doomed)} total")
    print(f"{never_swept} active companies have never been fully swept "
          f"(their listings are exempt until a DEEP run completes one)")
    _report(gone, dead, orphan, listings)

    over_cap = bool(total) and len(doomed) / total > SAFETY_FRACTION
    if over_cap and not force:
        raise SystemExit(
            f"ABORT: would prune {len(doomed)}/{total} ({len(doomed) / total:.0%} "
            f"> {SAFETY_FRACTION:.0%} cap) — refusing. Investigate before rerunning "
            f"(a mass mis-stamp or a stalled poll can trip this). "
            f"If this backlog is genuine, rerun with --force (optionally "
            f"--max-delete N) after confirming with --dry-run.")
    if over_cap:
        print(f"WARNING: --force overriding the {SAFETY_FRACTION:.0%} cap "
              f"({len(doomed)}/{total} = {len(doomed) / total:.0%})")

    # Oldest sighting first, so a bounded run retires the most certainly-dead
    # listings and any surprise shows up before the rest are touched.
    doomed.sort(key=_seen_epoch)
    if max_delete is not None and len(doomed) > max_delete:
        print(f"--max-delete {max_delete}: trimming from {len(doomed)} "
              f"(most-stale first; rerun to continue)")
        doomed = doomed[:max_delete]

    if dry_run:
        print(f"dry-run: nothing deleted ({len(doomed)} would be)")
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

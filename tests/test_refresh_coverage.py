"""Coverage plumbing: a truncated poll must never earn the prune-authoritative stamp."""
import json

from jobbot import refresh
from jobbot.ats.adapters import JobList, workday_fetch


class _Resp:
    def __init__(self, payload):
        self._p = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._p


def _board(n_total, titles=None):
    """A fake CXS that serves n_total postings, 20 per page, like the real one."""
    posts = [{"externalPath": f"/job/j{i}", "title": (titles or "Analyst"),
              "locationsText": "NY", "postedOn": "Posted Today"} for i in range(n_total)]

    def req(url, method="GET", body=None):
        if url.endswith("/jobs"):
            off = (body or {}).get("offset", 0)
            return _Resp({"jobPostings": posts[off:off + 20], "total": n_total})
        return _Resp({"jobPostingInfo": {}})  # detail enrichment
    return req


def _with_policy(req, full_sweep):
    req.policy = refresh.Policy(full_sweep=full_sweep)
    return req


def test_deep_sweeps_a_big_board_completely():
    """The exact failure mode: 900 postings is far past FAST's 500/term ceiling."""
    out = workday_fetch("acme.wd1/site", _with_policy(_board(900), full_sweep=True))
    assert isinstance(out, JobList)
    assert out.complete is True
    assert len(out) == 900


def test_fast_never_claims_completeness():
    """Even a tiny board: FAST's four search terms are not the whole board, so it
    must not authorize deletion (a hard_gate title matching no term would vanish)."""
    out = workday_fetch("acme.wd1/site", _with_policy(_board(5), full_sweep=False))
    assert out.complete is False


def test_deep_reports_incomplete_when_it_hits_the_page_ceiling(monkeypatch):
    monkeypatch.setattr("jobbot.ats.adapters._WD_DEEP_PAGES", 2)  # 40 postings max
    out = workday_fetch("acme.wd1/site", _with_policy(_board(900), full_sweep=True))
    assert out.complete is False
    assert len(out) == 40


def test_empty_board_is_complete():
    out = workday_fetch("acme.wd1/site", _with_policy(_board(0), full_sweep=True))
    assert out.complete is True and len(out) == 0


# --- _write: the two stamps stay independent ---------------------------------

def test_write_stamps_full_poll_only_for_complete_results(monkeypatch):
    upserts = []
    monkeypatch.setattr(refresh, "_chunked_upsert",
                        lambda t, rows, on_conflict, **kw: upserts.append((t, rows)))
    batch = [
        {"slug": "full", "ats": "workday", "status": "ok", "rows": [], "complete": True},
        {"slug": "trunc", "ats": "workday", "status": "ok", "rows": [], "complete": False},
    ]
    refresh._write(batch, {}, condemns=False)

    company_rows = [r for t, rows in upserts if t == "companies" for r in rows]
    polled = {r["company_slug"] for r in company_rows if "last_polled_at" in r}
    swept = {r["company_slug"] for r in company_rows if "last_full_poll_at" in r}
    assert polled == {"full", "trunc"}   # both answered
    assert swept == {"full"}             # only one was exhaustive


def test_plain_list_results_count_as_complete(monkeypatch):
    """Single-request ATSs return a plain list == the whole board."""
    upserts = []
    monkeypatch.setattr(refresh, "_chunked_upsert",
                        lambda t, rows, on_conflict, **kw: upserts.append((t, rows)))
    refresh._write([{"slug": "gh", "ats": "greenhouse", "status": "ok", "rows": []}],
                   {}, condemns=False)
    rows = [r for t, rows in upserts if t == "companies" for r in rows]
    assert any("last_full_poll_at" in r for r in rows)


# --- the enrichment staleness trap ------------------------------------------

def test_enriched_listing_keeps_its_description_on_a_re_poll():
    """A stored job whose detail fetch is skipped must still carry a description.

    Without this, evaluate()'s TECH gate saw an empty description, dropped the
    row, and last_seen_at was never bumped again — so a live job looked closed
    forever. That inflated workday to 78% "gone" and nearly deleted ~15.5k live
    listings.
    """
    from jobbot.ats.adapters import set_enriched, workday_fetch
    from jobbot.filters import evaluate

    canon = "https://acme.wd1.myworkdayjobs.com/en-US/site/job/j0"
    stored = "Pharmacy intern supporting clinical medical operations."
    set_enriched("workday", {canon: stored})
    try:
        req = _board(1, titles="Pharmacy Intern")
        req.policy = refresh.Policy(full_sweep=True)
        out = workday_fetch("acme.wd1/site", req)
        assert out[0]["canonical_url"] == canon
        assert out[0]["description"] == stored, "cached description was dropped"
        assert evaluate(out[0]["title"], out[0]["description"])[0] is True
    finally:
        set_enriched("workday", {})


def test_unenriched_listing_still_gets_a_detail_fetch():
    from jobbot.ats.adapters import set_enriched, workday_fetch
    set_enriched("workday", {})
    req = _board(1, titles="Software Engineering Intern")
    req.policy = refresh.Policy(full_sweep=True)
    out = workday_fetch("acme.wd1/site", req)
    assert len(out) == 1  # detail path exercised, no crash

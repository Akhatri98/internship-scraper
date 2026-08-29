import pytest

from jobbot import prune
from jobbot.prune import SAFETY_FRACTION, _classify, _seen_epoch
from jobbot.seed.domains import extract


def _co(slug, ats="workday", full=None, polled="2026-08-29T12:00:00+00:00", active=True):
    return {"company_slug": slug, "ats_source": ats, "last_polled_at": polled,
            "last_full_poll_at": full, "still_active": active}


def _lst(lid, slug, seen, ats="workday"):
    return {"id": lid, "canonical_url": f"https://x/{lid}", "company_slug": slug,
            "ats_source": ats, "last_seen_at": seen}


def _cmap(*cos):
    return {(c["company_slug"], c["ats_source"]): c for c in cos}


# --- the core safety property -------------------------------------------------

def test_never_gone_without_a_full_sweep():
    """A board polled OK but never swept exhaustively cannot lose listings.

    This is the regression that broke prune for 47 days: a truncated Workday poll
    stamped last_polled_at, and every listing past the page cap looked closed.
    """
    cmap = _cmap(_co("acme.wd1/site", full=None))
    gone, dead, orphan = _classify([_lst("1", "acme.wd1/site", "2026-01-01T00:00:00+00:00")], cmap)
    assert (gone, dead, orphan) == ([], [], [])


def test_gone_when_a_full_sweep_postdates_the_sighting():
    cmap = _cmap(_co("acme.wd1/site", full="2026-08-29T12:00:00+00:00"))
    gone, _, _ = _classify([_lst("1", "acme.wd1/site", "2026-08-01T00:00:00+00:00")], cmap)
    assert [l["id"] for l in gone] == ["1"]


def test_stale_margin_absorbs_intra_run_skew():
    """Swept 30min after the sighting -> still live (margin is 2h)."""
    cmap = _cmap(_co("acme.wd1/site", full="2026-08-29T12:30:00+00:00"))
    gone, _, _ = _classify([_lst("1", "acme.wd1/site", "2026-08-29T12:00:00+00:00")], cmap)
    assert gone == []


def test_dead_board_and_orphan_do_not_need_a_sweep():
    """Both buckets are independent of poll coverage."""
    cmap = _cmap(_co("dead.wd1/site", full=None, active=False))
    listings = [_lst("1", "dead.wd1/site", "2026-08-01T00:00:00+00:00"),
                _lst("2", "nosuch.wd1/site", "2026-08-01T00:00:00+00:00")]
    gone, dead, orphan = _classify(listings, cmap)
    assert [l["id"] for l in dead] == ["1"]
    assert [l["id"] for l in orphan] == ["2"]
    assert gone == []


# --- the safety cap and its override -----------------------------------------

class _FakeDB:
    def __init__(self, companies, listings):
        self._c, self._l = companies, listings
        self.deleted = []

    def select_all(self, table, params=None):
        return list(self._c if table == "companies" else self._l)

    def delete(self, table, match):
        self.deleted += match["id"].removeprefix("in.(").rstrip(")").split(",")


@pytest.fixture
def over_cap(monkeypatch):
    """One live board, fully swept, with every listing stale -> 100% doomed."""
    companies = [_co("acme.wd1/site", full="2026-08-29T12:00:00+00:00")]
    listings = [_lst(str(i), "acme.wd1/site", f"2026-08-{i + 1:02d}T00:00:00+00:00")
                for i in range(10)]
    fake = _FakeDB(companies, listings)
    monkeypatch.setattr(prune, "db", fake)
    return fake


def test_cap_aborts_without_force(over_cap):
    with pytest.raises(SystemExit) as e:
        prune.run_prune()
    assert "ABORT" in str(e.value) and "--force" in str(e.value)
    assert over_cap.deleted == []


def test_force_overrides_the_cap(over_cap):
    assert prune.run_prune(force=True) == 10
    assert len(over_cap.deleted) == 10


def test_max_delete_bounds_the_blast_radius_most_stale_first(over_cap):
    assert prune.run_prune(force=True, max_delete=3) == 3
    # ids 0,1,2 carry the oldest last_seen_at
    assert sorted(over_cap.deleted) == ["0", "1", "2"]


def test_dry_run_writes_nothing(over_cap):
    assert prune.run_prune(dry_run=True, force=True) == 10
    assert over_cap.deleted == []


def test_under_cap_needs_no_force(monkeypatch):
    companies = [_co("acme.wd1/site", full="2026-08-29T12:00:00+00:00")]
    listings = ([_lst("old", "acme.wd1/site", "2026-01-01T00:00:00+00:00")]
                + [_lst(str(i), "acme.wd1/site", "2026-08-29T11:59:00+00:00")
                   for i in range(10)])
    fake = _FakeDB(companies, listings)
    monkeypatch.setattr(prune, "db", fake)
    assert 1 / 11 < SAFETY_FRACTION
    assert prune.run_prune() == 1
    assert fake.deleted == ["old"]


def test_seen_epoch_sorts_missing_timestamps_oldest():
    assert _seen_epoch({"last_seen_at": None}) == float("-inf")
    assert _seen_epoch({"last_seen_at": "2026-08-29T12:00:00+00:00"}) > 0
    # naive timestamps must not explode the sort
    assert _seen_epoch({"last_seen_at": "2026-08-29T12:00:00"}) > 0


# --- the duplicate-slug source ------------------------------------------------

def test_workday_slug_is_lowercased():
    """Case-variant slugs minted two identities for one board (334 pairs, ~8.4k
    twin listing rows). CXS is case-insensitive, so lowercase is canonical."""
    a = extract("https://cvshealth.wd1.myworkdayjobs.com/en-US/CVS_Health_Careers/job/x")
    b = extract("https://cvshealth.wd1.myworkdayjobs.com/en-US/cvs_health_careers/job/x")
    assert a == b == ("workday", "cvshealth.wd1/cvs_health_careers")

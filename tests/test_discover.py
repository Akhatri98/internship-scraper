"""Discovery must fail loudly when Common Crawl can't answer: an index outage used
to read as "+0 new" on every domain and a green run — the same as a quiet month."""
import json

import pytest

from jobbot import db
from jobbot.discover import commoncrawl, run
from jobbot.discover.commoncrawl import IndexUnavailable, iter_urls, num_pages


class _Resp:
    def __init__(self, status, body=""):
        self.status_code = status
        self.text = body

    def json(self):
        return json.loads(self.text)


class _Session:
    """Answers CDX requests from a {page_or_"count": (status, body)} script."""
    def __init__(self, script):
        self.script = script

    def get(self, url, params=None, headers=None, timeout=None):
        key = "count" if params.get("showNumPages") else params["page"]
        return _Resp(*self.script[key])


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(commoncrawl.time, "sleep", lambda s: None)


def _lines(*urls):
    return "\n".join(json.dumps({"url": u}) for u in urls)


def test_num_pages_outage_raises_not_zero():
    with pytest.raises(IndexUnavailable, match="HTTP 504"):
        num_pages("jobs.gem.com/*", "idx", _Session({"count": (504, "")}))


def test_num_pages_no_captures_is_a_real_zero():
    assert num_pages("jobs.gem.com/*", "idx", _Session({"count": (404, "")})) == 0
    assert num_pages("jobs.gem.com/*", "idx", _Session({"count": (200, '{"pages": 3}')})) == 3


def test_iter_urls_reads_past_a_bad_page_then_raises():
    sess = _Session({"count": (200, '{"pages": 3}'),
                     0: (200, _lines("https://jobs.gem.com/a")),
                     1: (504, ""),
                     2: (200, _lines("https://jobs.gem.com/c"))})
    got = []
    with pytest.raises(IndexUnavailable, match="1/3 pages"):
        for u in iter_urls("jobs.gem.com/*", "idx", session=sess):
            got.append(u)
    assert got == ["https://jobs.gem.com/a", "https://jobs.gem.com/c"]  # nothing lost


@pytest.fixture
def fake_db(monkeypatch):
    upserted = []
    monkeypatch.setattr(db, "select_all", lambda *a, **k: [])
    monkeypatch.setattr(db, "upsert", lambda table, rows, **k: upserted.extend(rows))
    return upserted


def test_run_discover_outage_fails_but_keeps_what_it_read(monkeypatch, fake_db):
    def fake_iter(pattern, index, **k):
        if pattern.startswith("jobs.gem.com"):
            yield "https://jobs.gem.com/deep-infra"
        else:
            raise IndexUnavailable(f"{pattern}: page count failed after 4 tries (HTTP 504)")
    monkeypatch.setattr(run, "iter_urls", fake_iter)
    domains = [("jobs.gem.com", "gem", "path"), ("jobs.lever.co", "lever", "path")]
    with pytest.raises(SystemExit, match="1/2 domain"):
        run.run_discover(domains=domains, index="idx")
    assert fake_db == [{"company_slug": "deep-infra", "ats_source": "gem"}]


def test_run_discover_quiet_month_stays_green(monkeypatch, fake_db):
    monkeypatch.setattr(run, "iter_urls", lambda *a, **k: iter(()))
    assert run.run_discover(domains=[("jobs.gem.com", "gem", "path")], index="idx") == 0

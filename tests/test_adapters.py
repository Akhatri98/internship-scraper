"""Parser tests for the Stage 7 ATSs (bamboohr JSON; jazzhr/jobvite HTML;
workday CXS postings) plus the workday composite-slug extraction."""
from datetime import datetime, timedelta, timezone

from jobbot.ats.adapters import (bamboohr_jobs, jazzhr_jobs, jobvite_jobs,
                                 workday_jobs, _workday_posted)
from jobbot.seed.domains import extract


def test_bamboohr_parses_list():
    data = {"meta": {"totalCount": 1}, "result": [{
        "id": "530", "jobOpeningName": "Software Intern",
        "departmentLabel": "Engineering", "employmentStatusLabel": "Intern",
        "atsLocation": {"country": "United States", "state": "Illinois", "city": "Chicago"},
        "isRemote": None,
    }]}
    (j,) = bamboohr_jobs(data, "acme")
    assert j["canonical_url"] == "https://acme.bamboohr.com/careers/530"
    assert j["title"] == "Software Intern"
    assert j["employment_type"] == "Intern"
    assert j["location"] == "Chicago, Illinois"
    assert j["country"] == "United States"


def test_bamboohr_remote_and_empty():
    data = {"result": [{"id": 7, "jobOpeningName": "X", "isRemote": True,
                        "atsLocation": {"country": None, "state": None, "city": None}}]}
    (j,) = bamboohr_jobs(data, "acme")
    assert j["location"] == "Remote"
    assert bamboohr_jobs({}, "acme") == []


_JAZZ_HTML = """
<li class="list-group-item">
  <h3 class='list-group-item-heading'>
      <a href="https://acme.applytojob.com/apply/evgnhR5LkV/Electrical-Engineer-PCB">
          Electrical Engineer &amp; PCB
      </a>
  </h3>
  <ul class='list-inline list-group-item-text'>
      <li><i class='fa fa-map-marker'></i>Austin, TX</li>
  </ul>
</li>
<li class="list-group-item">
  <h3 class='list-group-item-heading'>
      <a href="https://acme.applytojob.com/apply/XyZ123abc/No-Location-Role">No Location Role</a>
  </h3>
</li>
"""


def test_jazzhr_parses_items():
    jobs = jazzhr_jobs(_JAZZ_HTML, "acme")
    assert len(jobs) == 2
    assert jobs[0]["canonical_url"] == "https://acme.applytojob.com/apply/evgnhR5LkV"
    assert jobs[0]["title"] == "Electrical Engineer & PCB"  # entities unescaped
    assert jobs[0]["location"] == "Austin, TX"
    assert jobs[0]["country"] == "United States"
    assert jobs[1]["location"] == ""


_JV_HTML = """
<tr>
  <td class="jv-job-list-name">
      <a href="/acme/job/ojynAfwy">(CW) Accounts Payable Analyst</a>
  </td>
  <td class="jv-job-list-location">
      Dublin,
      Ireland
  </td>
</tr>
"""


def test_jobvite_parses_rows_and_pages():
    jobs = jobvite_jobs([_JV_HTML, _JV_HTML.replace("ojynAfwy", "abc").replace("Dublin", "Cork")], "acme")
    assert len(jobs) == 2
    assert jobs[0]["canonical_url"] == "https://jobs.jobvite.com/acme/job/ojynAfwy"
    assert jobs[0]["title"] == "(CW) Accounts Payable Analyst"
    assert jobs[0]["location"] == "Dublin, Ireland"  # whitespace collapsed
    assert jobs[0]["country"] == "Ireland"
    assert jobvite_jobs("<html>no rows</html>", "acme") == []


def test_workday_jobs_builds_urls_from_composite_slug():
    postings = [{"title": "Fluid Systems Intern", "externalPath": "/job/Seattle-WA/Intern_R123",
                 "locationsText": "Seattle, WA", "postedOn": "Posted Yesterday"}]
    (j,) = workday_jobs(postings, "blueorigin.wd5/BlueOrigin")
    assert j["canonical_url"] == ("https://blueorigin.wd5.myworkdayjobs.com"
                                  "/en-US/BlueOrigin/job/Seattle-WA/Intern_R123")
    assert j["company"] == "Blueorigin"
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    assert j["posted_at"] == yesterday


def test_workday_posted_parsing():
    assert _workday_posted("Posted Today") == datetime.now(timezone.utc).date().isoformat()
    assert _workday_posted("Posted 30+ Days Ago") is None  # unknown, not "30"
    assert _workday_posted(None) is None
    three = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    assert _workday_posted("Posted 3 Days Ago") == three


def test_extract_workday_composite():
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/en-US/BlueOrigin/job/x_R1") == \
        ("workday", "blueorigin.wd5/BlueOrigin")
    assert extract("https://tamus.wd1.myworkdayjobs.com/TEEX_External") == \
        ("workday", "tamus.wd1/TEEX_External")
    # site case is preserved, host lowered
    assert extract("https://Acme.WD3.myworkdayjobs.com/fr/SiteName") == \
        ("workday", "acme.wd3/SiteName")
    # unusable: bare host, wday internals, missing wdN
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/") is None
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/X/jobs") is None
    assert extract("https://blueorigin.myworkdayjobs.com/en-US/Site") is None

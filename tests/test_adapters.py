"""Parser tests for the Stage 7 ATSs (bamboohr JSON; jazzhr/jobvite HTML;
workday CXS postings) plus the workday composite-slug extraction, the teamtailor
_jobposting enrichment, the SmartRecruiters detail-description extraction, and
the gem job-board feed + its case-sensitive slug extraction."""
from datetime import datetime, timedelta, timezone

from jobbot.ats.adapters import (bamboohr_jobs, jazzhr_jobs, jobvite_jobs,
                                 workday_jobs, _workday_posted, teamtailor_jobs,
                                 _sr_detail_desc, gem_jobs)
from jobbot.filters import evaluate, hard_gate
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


def test_workday_jobs_uses_detail_when_enriched():
    postings = [{
        "title": "Software Engineering Intern", "externalPath": "/job/Seattle/Intern_R1",
        "locationsText": "Seattle, WA", "postedOn": "Posted 30+ Days Ago",
        "_detail": {"jobDescription": "<p>Build <b>rockets</b></p>", "location": "Greater Seattle Area",
                    "country": {"descriptor": "United States of America"}, "startDate": "2026-06-15"},
    }]
    (j,) = workday_jobs(postings, "blueorigin.wd5/BlueOrigin")
    assert j["description"] == "Build rockets"           # real desc, not empty
    assert j["location"] == "Greater Seattle Area"       # detail location wins
    assert j["country"] == "United States"               # descriptor normalized
    assert j["posted_at"] == "2026-06-15"                # exact date beats "30+ Days"


def test_workday_jobs_falls_back_without_detail():
    # no _detail -> list-level behavior (empty desc, relative date, free-text loc)
    postings = [{"title": "Data Intern", "externalPath": "/job/x_R2",
                 "locationsText": "Austin, TX", "postedOn": "Posted Today"}]
    (j,) = workday_jobs(postings, "acme.wd1/Careers")
    assert j["description"] == ""
    assert j["location"] == "Austin, TX"
    assert j["posted_at"] == datetime.now(timezone.utc).date().isoformat()


def test_workday_posted_parsing():
    assert _workday_posted("Posted Today") == datetime.now(timezone.utc).date().isoformat()
    assert _workday_posted("Posted 30+ Days Ago") is None  # unknown, not "30"
    assert _workday_posted(None) is None
    three = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    assert _workday_posted("Posted 3 Days Ago") == three


def test_teamtailor_recovers_location_pay_from_jobposting():
    data = {"title": "Acme", "items": [{
        "url": "https://acme.teamtailor.com/jobs/123-data-intern",
        "title": "Data Intern",
        "content_html": "<p>Join us</p>",
        "date_published": "2026-06-01",
        "location": None,  # top-level location is ~always absent
        "_jobposting": {
            "jobLocation": [{"@type": "Place", "address": {
                "addressLocality": "Paris", "addressRegion": "France", "addressCountry": "FR"}}],
            "baseSalary": {"currency": "EUR", "value": {
                "unitText": "MONTH", "minValue": "1500", "maxValue": "1700"}},
        },
    }]}
    (j,) = teamtailor_jobs(data, "acme")
    assert j["location"] == "Paris, France"
    assert j["country"] == "France"           # from ISO2 addressCountry
    assert j["pay"] == "EUR 1500–1700/month"  # unitText lowercased
    assert j["company"] == "Acme"


def test_teamtailor_single_value_pay_and_no_jobposting():
    data = {"title": "Acme", "items": [
        {"url": "https://acme.teamtailor.com/jobs/1-a", "title": "A", "content_html": "<p>x</p>",
         "_jobposting": {"baseSalary": {"currency": "EUR", "value": {"unitText": "DAY", "value": "500"}}}},
        {"url": "https://acme.teamtailor.com/jobs/2-b", "title": "B"},  # no _jobposting at all
    ]}
    a, b = teamtailor_jobs(data, "acme")
    assert a["pay"] == "EUR 500/day"
    assert b["pay"] is None and b["location"] == "" and b["title"] == "B"


def test_smartrecruiters_detail_desc_extraction():
    detail = {"jobAd": {"sections": {
        "jobDescription": {"text": "<p>Build <strong>things</strong></p>"},
        "qualifications": {"text": "<ul><li>Python</li></ul>"},
        "additionalInformation": {"text": ""},
    }}}
    assert _sr_detail_desc(detail) == "Build things Python"
    assert _sr_detail_desc({}) == ""  # missing sections -> empty, not a crash


def test_hard_gate_is_title_only_necessary_condition():
    assert hard_gate("Software Engineering Intern") == ["intern"]
    assert hard_gate("Senior Backend Engineer") == []          # no student term -> no fetch
    assert hard_gate("Engineer", "Internship") == ["intern"]   # ATS employment type counts
    assert hard_gate("Internal Audit Manager") == []           # word-boundary: not "intern"


def test_extract_workday_composite():
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/en-US/BlueOrigin/job/x_R1") == \
        ("workday", "blueorigin.wd5/blueorigin")
    assert extract("https://tamus.wd1.myworkdayjobs.com/TEEX_External") == \
        ("workday", "tamus.wd1/teex_external")
    # Site case is LOWERED now, like every other ATS: CXS is case-insensitive,
    # so preserving it only minted a SECOND identity for one board — two
    # companies rows and two canonical_urls per job, the twins rotting in
    # prune's "gone" bucket. See scripts/dedupe_workday.py.
    assert extract("https://Acme.WD3.myworkdayjobs.com/fr/SiteName") == \
        ("workday", "acme.wd3/sitename")
    # the same board discovered under two casings is now ONE slug
    assert (extract("https://cvshealth.wd1.myworkdayjobs.com/en-US/CVS_Health_Careers/job/x")
            == extract("https://cvshealth.wd1.myworkdayjobs.com/en-US/cvs_health_careers/job/x"))
    # unusable: bare host, wday internals, missing wdN
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/") is None
    assert extract("https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/X/jobs") is None
    assert extract("https://blueorigin.myworkdayjobs.com/en-US/Site") is None


# Trimmed from a live api.gem.com/job_board/v0/soeffects/job_posts/ entry.
_GEM_POST = {
    "id": "am9icG9zdDqLIuZagE8SU-HqhGf7TGYo",
    "absolute_url": "https://jobs.gem.com/soeffects/am9icG9zdDqLIuZagE8SU-HqhGf7TGYo",
    "title": "Electrical Engineering Intern (Summer 2027)",
    "content": "<p>Design <strong>PCBs</strong> &amp; test boards.</p>",
    "content_plain": "Design PCBs & test boards.",
    "first_published_at": "2026-07-19T02:39:49.294Z",
    "created_at": "2026-07-18T22:00:00.000Z",
    "employment_type": "intern",
    "location_type": "in_office",
    "location": {"name": "El Segundo, United States"},
    "offices": [{"name": "El Segundo, CA", "location": {"name": "El Segundo, United States"}},
                {"name": "Redmond, WA", "location": {"name": "Redmond, United States"}}],
    "departments": [{"id": "x", "name": "Engineering"}],
}


def test_gem_parses_post():
    (j,) = gem_jobs([_GEM_POST], "soeffects")
    assert j["canonical_url"] == "https://jobs.gem.com/soeffects/am9icG9zdDqLIuZagE8SU-HqhGf7TGYo"
    assert j["raw_url"] == _GEM_POST["absolute_url"]
    assert j["description"] == "Design PCBs & test boards."  # tags stripped, entities unescaped
    assert j["posted_at"] == "2026-07-19T02:39:49.294Z"
    assert j["location"] == "El Segundo, United States"     # primary office only
    assert j["country"] == "United States"
    assert j["company"] == "Soeffects"
    assert j["pay"] is None
    assert evaluate(j["title"], j["description"], j["employment_type"])[0]


def test_gem_intern_type_passes_hard_gate_without_title_term():
    # gem tags employment_type "intern" natively; that alone satisfies HARD
    post = {**_GEM_POST, "title": "Hardware Engineering, Summer 2027"}
    (j,) = gem_jobs([post], "soeffects")
    assert hard_gate(j["title"], j["employment_type"]) == ["intern"]
    (ft,) = gem_jobs([{**post, "employment_type": "full_time"}], "soeffects")
    assert hard_gate(ft["title"], ft["employment_type"]) == []


def test_gem_country_formats():
    def country(name):
        (j,) = gem_jobs([{"id": "1", "title": "X", "location": {"name": name}}], "acme")
        return j["country"]
    assert country("United States - Remote") == "United States"
    assert country("Sofia, Bulgaria") == "Bulgaria"
    assert country("Honduras - Remote") == "Honduras"  # long tail: not in geo's tables
    assert country("Remote") is None


def test_gem_numeric_id_empty_board_and_junk():
    # boards migrated from greenhouse keep numeric post ids
    (j,) = gem_jobs([{"id": "4965519002", "title": "Software Engineer"}], "gem")
    assert j["canonical_url"] == "https://jobs.gem.com/gem/4965519002"
    assert j["location"] == "" and j["country"] is None and j["description"] == ""
    assert gem_jobs([], "gem") == []                     # live but empty board
    assert gem_jobs([{"title": "no id"}], "gem") == []
    assert gem_jobs({"code": 404}, "gem") == []          # error body, not a list


def test_extract_gem_keeps_slug_case():
    assert extract("https://jobs.gem.com/deep-infra/am9icG9zdDq") == ("gem", "deep-infra")
    # vanity paths are case-sensitive (wrong case 404s), so never lowercase them
    assert extract("https://jobs.gem.com/AcmeCo") == ("gem", "AcmeCo")
    assert extract("https://jobs.gem.com/") is None
    assert extract("https://jobs.gem.com/Static/x.js") is None  # generic filter still applies

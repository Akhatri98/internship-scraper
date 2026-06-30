from jobbot.ats.parse import ats_from_url, normalize_url, slug_from_url


def test_ats_detection():
    assert ats_from_url("https://boards.greenhouse.io/stripe") == "greenhouse"
    assert ats_from_url("https://job-boards.greenhouse.io/stripe/jobs/123") == "greenhouse"
    assert ats_from_url("https://jobs.lever.co/figma") == "lever"
    assert ats_from_url("https://jobs.ashbyhq.com/openai") == "ashby"
    assert ats_from_url("https://www.linkedin.com/jobs/view/123") is None
    assert ats_from_url("https://example.com") is None


def test_slug_path_forms():
    assert slug_from_url("https://boards.greenhouse.io/stripe") == "stripe"
    assert slug_from_url("https://boards.greenhouse.io/Stripe/jobs/456") == "stripe"
    assert slug_from_url("https://job-boards.greenhouse.io/anthropic/jobs/789") == "anthropic"
    assert slug_from_url("https://jobs.lever.co/figma/0c2a5f9e-uuid") == "figma"
    assert slug_from_url("https://jobs.lever.co/figma/") == "figma"
    assert slug_from_url("https://jobs.ashbyhq.com/openai/some-uuid") == "openai"


def test_slug_unknown_host():
    assert slug_from_url("https://example.com/foo") is None
    assert slug_from_url("https://boards.greenhouse.io/") is None


def test_greenhouse_embed_form():
    assert slug_from_url("https://boards.greenhouse.io/embed/job_board?for=acme") == "acme"


def test_normalize_strips_query_and_fragment():
    assert (
        normalize_url("https://boards.greenhouse.io/stripe/jobs/1?gh_src=x&utm_source=y#apply")
        == "https://boards.greenhouse.io/stripe/jobs/1"
    )


def test_normalize_forces_https_and_lowercases_host_only():
    # host lowercased, path case preserved (paths can be case-sensitive)
    assert normalize_url("http://Boards.Greenhouse.IO/Stripe/") == "https://boards.greenhouse.io/Stripe"


def test_normalize_trailing_slash_and_port():
    assert normalize_url("https://jobs.lever.co:443/figma/") == "https://jobs.lever.co/figma"


def test_normalize_idempotent():
    u = "https://jobs.ashbyhq.com/openai/abc?x=1"
    assert normalize_url(normalize_url(u)) == normalize_url(u)


def test_normalize_none():
    assert normalize_url(None) is None
    assert normalize_url("") is None

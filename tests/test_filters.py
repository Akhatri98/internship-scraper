from jobbot.filters import evaluate


def test_intern_plus_tech_passes():
    ok, kw = evaluate("Software Engineering Intern", "Work on backend systems")
    assert ok
    assert "intern" in kw and "software" in kw


def test_intern_without_tech_fails():
    ok, kw = evaluate("Marketing Intern", "Help with social media campaigns")
    assert not ok


def test_tech_without_intern_fails():
    ok, _ = evaluate("Senior Software Engineer", "Backend role")
    assert not ok


def test_internal_does_not_trigger_intern():
    # 'internal' must not satisfy the intern gate
    ok, _ = evaluate("Internal Tools Engineer", "Build internal software")
    assert not ok


def test_international_does_not_trigger_intern():
    ok, _ = evaluate("International Data Analyst", "data analytics work")
    assert not ok


def test_cooperative_does_not_trigger_coop():
    ok, _ = evaluate("Cooperative Software Role", "developer position")
    assert not ok


def test_coop_passes():
    ok, kw = evaluate("Data Co-op", "Machine learning pipelines")
    assert ok
    assert "co-op" in kw and "data" in kw


def test_employment_type_signal_passes():
    ok, kw = evaluate("Software Engineer", "Build developer tools", employment_type="Intern")
    assert ok
    assert "intern" in kw


def test_new_grad_passes():
    ok, kw = evaluate("New Grad Software Engineer", "developer role")
    assert ok
    assert "new grad" in kw


def test_keywords_deduped_and_sorted():
    ok, kw = evaluate("AI Intern", "AI and machine learning, AI again")
    assert ok
    assert kw == sorted(set(kw))

from jobbot.filters import evaluate, hard_gate


def test_intern_plus_tech_passes():
    ok, kw = evaluate("Software Engineering Intern", "Work on backend systems")
    assert ok
    assert "intern" in kw and "software" in kw


def test_marketing_intern_now_passes():
    # Post-broadening: marketing is a covered field, so this should surface.
    ok, kw = evaluate("Marketing Intern", "Help with social media campaigns")
    assert ok
    assert "intern" in kw and "marketing" in kw


def test_finance_coop_passes():
    ok, kw = evaluate("Finance Co-op", "Support FP&A and financial modeling")
    assert ok
    assert "co-op" in kw and "finance" in kw


def test_mechanical_intern_passes():
    ok, kw = evaluate("Mechanical Engineering Intern", "CAD design and prototyping")
    assert ok
    assert "mechanical" in kw or "engineering" in kw


def test_non_professional_intern_still_fails():
    # No professional-field term in title or description -> still excluded.
    ok, _ = evaluate("Kitchen Intern", "Prep food and clean the line each shift")
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


# --- new grad / early career (titles below are real postings) ----------------

def test_grad_phrasings_beyond_new_grad():
    assert "new grad" in hard_gate("Associate Software Engineer (College Grad 2027)")
    assert "new grad" in hard_gate("Software Engineer (2027 University Grad)")
    assert "new grad" in hard_gate("Auditor (Fresh Grad) 2027")
    # UK schemes put "Graduate" on either side of the role
    assert "new grad" in hard_gate("Graduate Civil Engineer - Highways")
    assert "new grad" in hard_gate("Civil Engineering Graduate")


def test_graduate_school_roles_are_not_new_grad():
    assert hard_gate("Admissions Counselor II - Graduate Admissions") == []
    assert hard_gate("Graduate Research Assistant") == []
    assert hard_gate("Post-Graduate Fellow") == []
    assert hard_gate("Instructor for Graduate Course in Organizational Ethics") == []


def test_early_careers_plural_and_early_talent():
    # "Early Careers" (UK plural) used to slip past `career\b`
    assert hard_gate("Engineer, Field Service (Early Careers)") == ["early career"]
    assert hard_gate("Site Reliability Engineer (SRE) - Early Talent") == ["early career"]
    assert hard_gate("Early in Career Development Programme - Marketing 2027") == ["early career"]


def test_staff_who_run_student_programs_are_excluded():
    assert hard_gate("Regional Early Careers/University Recruiter") == []
    assert hard_gate("Talent Acquisition Associate, Early Careers") == []
    assert hard_gate("Graduate Program Coordinator") == []


def test_summer_analyst_is_an_internship():
    ok, kw = evaluate("2027 Private Equity Summer Analyst", "investment due diligence")
    assert ok and "intern" in kw


# --- entry level: needs the field in the TITLE ------------------------------

def test_entry_level_markers_with_title_field_pass():
    for title in ("Entry-Level Civil Engineer", "Junior Software Developer", "Jr. Web Developer",
                  "Data Scientist I", "Software Engineer I/II", "Analyst - Level 1",
                  "Associate Product Manager", "Associate Scientist", "Junior Project Manager - Marketing"):
        ok, kw = evaluate(title, "")
        assert ok and "entry level" in kw, title


def test_entry_level_markers_without_title_field_fail():
    # the description would satisfy the OR-bag — the title must, for LEVEL terms
    desc = "logistics operations in a fast-paced business"
    for title in ("Entry Level Loan Processor", "Warehouse Associate I",
                  "Commercial Door Installer Trainee", "Junior Sous Chef"):
        assert evaluate(title, desc) == (False, []), title
        assert hard_gate(title) == [], title  # so detail fetchers skip them too


def test_recent_grads_welcome_is_a_level_hint():
    desc = "logistics and supply chain"
    assert not evaluate("CDL-A Truck Driver | Solo, Mentor or Recent Graduates", desc)[0]
    assert not evaluate("OTR Fleet Driver - Recent CDL Grads", desc)[0]
    assert evaluate("Data Analyst (Recent Grad)", "")[0]


def test_level_one_is_not_ii_or_an_ampersand():
    assert hard_gate("Software Engineer II") == []
    assert hard_gate("Software Engineer IV") == []
    assert hard_gate("Commissioning Engineer - I&C (Instrumentation & Control)") == []
    assert hard_gate("Engineer In Training") == []
    assert hard_gate("Associate Technical Services Engineer II (Cloud)") == []


def test_senior_markers_veto_entry_level():
    assert hard_gate("(Senior) Engineer I, Global Product Support") == []
    assert hard_gate("Snr IT Analyst I") == []
    assert hard_gate("Associate Director, Software Engineering") == []

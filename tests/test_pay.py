from jobbot.pay import format_salary, is_unpaid


def test_unpaid_strong_signals():
    assert is_unpaid("Marketing Intern", "This is an unpaid internship for the summer")
    assert is_unpaid("Research Role", "The position is unpaid but offers great mentorship")
    assert is_unpaid("Intern", "No compensation is provided for this role")
    assert is_unpaid("Design Intern", "This is a volunteer position")
    assert is_unpaid("Intern", "Available for academic credit only")


def test_unpaid_ignores_boilerplate():
    assert not is_unpaid("Software Intern", "Benefits include unpaid leave and PTO")
    assert not is_unpaid("Data Intern", "We offer generous unpaid time off")
    assert not is_unpaid("Finance Intern", "Competitive compensation and benefits")
    assert not is_unpaid("Engineer", "")


def test_format_salary():
    assert format_salary("2400", "3000", "month", "EUR") == "EUR 2400–3000/month"
    assert format_salary("50000", None, "year", "USD") == "USD 50000/year"
    assert format_salary(None, "80000", "year", "") == "80000/year"
    assert format_salary(None, None, "year", "USD") is None
    assert format_salary("0", "0", "month", "EUR") is None
    assert format_salary("1500", "1500", "month", "EUR") == "EUR 1500/month"

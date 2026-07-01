from jobbot.util import display_name


def test_display_name_deslugifies():
    assert display_name("brooks-running") == "Brooks Running"
    assert display_name("acme_corp") == "Acme Corp"
    assert display_name("stripe") == "Stripe"


def test_display_name_drops_numeric_suffix():
    assert display_name("zotefoams-1734537268") == "Zotefoams"


def test_display_name_empty():
    assert display_name(None) is None
    assert display_name("") is None

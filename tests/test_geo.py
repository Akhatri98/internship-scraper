from jobbot.geo import country_of


def test_structured_iso2_code():
    assert country_of("us") == "United States"
    assert country_of("GB") == "United Kingdom"
    assert country_of("de") == "Germany"


def test_structured_name_and_alias():
    assert country_of("United States of America") == "United States"
    assert country_of("England") == "United Kingdom"
    assert country_of("Philippines") == "Philippines"


def test_structured_non_country_ignored():
    assert country_of("Remote") is None
    assert country_of("Various") is None
    assert country_of("Any Location") is None
    assert country_of(None) is None


def test_localized_country_names_normalized():
    assert country_of("Nederland") == "Netherlands"
    assert country_of("Deutschland") == "Germany"
    assert country_of("Allemagne") == "Germany"
    assert country_of("Brasil") == "Brazil"
    assert country_of("Frankrijk") == "France"
    assert country_of("Latvija") == "Latvia"
    assert country_of("Lietuva") == "Lithuania"


def test_freetext_city_state_is_us():
    assert country_of(None, "San Francisco, CA") == "United States"
    assert country_of(None, "New York, NY, United States") == "United States"


def test_freetext_trailing_country():
    assert country_of(None, "London, UK") == "United Kingdom"
    assert country_of(None, "Berlin, Germany") == "Germany"
    assert country_of(None, "Remote - US") == "United States"


def test_freetext_unknown_returns_none():
    assert country_of(None, "Bengaluru, KA") is None
    assert country_of(None, "") is None


def test_structured_beats_freetext():
    assert country_of("ca", "Toronto") == "Canada"

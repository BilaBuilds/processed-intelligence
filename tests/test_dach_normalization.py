import pytest

from scripts.dach.normalize_dach_tender import normalize_dach_tender


def test_germany_default_language_and_currency():
    tender = normalize_dach_tender({"title": "Road works"}, "fixture", "Germany")

    assert tender["language"] == "de"
    assert tender["currency"] == "EUR"


def test_austria_default_language_and_currency():
    tender = normalize_dach_tender({"title": "School works"}, "fixture", "Austria")

    assert tender["language"] == "de"
    assert tender["currency"] == "EUR"


def test_switzerland_default_currency_and_unknown_language():
    tender = normalize_dach_tender({"title": "Drainage works"}, "fixture", "Switzerland")

    assert tender["language"] == "unknown"
    assert tender["currency"] == "CHF"


def test_invalid_country_raises_value_error():
    with pytest.raises(ValueError):
        normalize_dach_tender({}, "fixture", "France")


def test_cpv_codes_always_list():
    tender = normalize_dach_tender({"cpv": "45233141,45233142"}, "fixture", "Germany")

    assert tender["cpv_codes"] == ["45233141", "45233142"]


def test_missing_optional_fields_do_not_crash():
    tender = normalize_dach_tender({}, "fixture", "Austria")

    assert tender["title"] == ""
    assert tender["buyer"] == ""
    assert tender["deadline"] is None
    assert tender["value"] is None
    assert tender["source_url"] == ""


def test_priority_defaults_to_unscored_and_reasons_empty():
    tender = normalize_dach_tender({"title": "Bridge works"}, "fixture", "Switzerland")

    assert tender["priority"] == "UNSCORED"
    assert tender["reasons"] == []

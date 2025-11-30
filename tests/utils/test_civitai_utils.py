from py.utils.civitai_utils import build_license_flags, resolve_license_info, resolve_license_payload


def test_resolve_license_payload_defaults():
    payload, flags = resolve_license_info({})

    assert payload["allowNoCredit"] is True
    assert payload["allowDerivatives"] is True
    assert payload["allowDifferentLicense"] is True
    assert payload["allowCommercialUse"] == ["Sell"]
    assert flags == 127


def test_build_license_flags_custom_values():
    source = {
        "allowNoCredit": False,
        "allowCommercialUse": {"Image", "Sell"},
        "allowDerivatives": False,
        "allowDifferentLicense": False,
    }

    payload = resolve_license_payload(source)
    assert payload["allowNoCredit"] is False
    assert set(payload["allowCommercialUse"]) == {"Image", "Sell"}
    assert payload["allowDerivatives"] is False
    assert payload["allowDifferentLicense"] is False

    flags = build_license_flags(source)
    # Sell automatically enables all commercial bits including image.
    assert flags == 30


def test_build_license_flags_respects_commercial_hierarchy():
    base = {
        "allowNoCredit": False,
        "allowDerivatives": False,
        "allowDifferentLicense": False,
    }

    assert build_license_flags({**base, "allowCommercialUse": []}) == 0
    # Rent adds rent and rentcivit permissions.
    assert build_license_flags({**base, "allowCommercialUse": ["Rent"]}) == 12
    # RentCivit alone should only set its own bit.
    assert build_license_flags({**base, "allowCommercialUse": ["RentCivit"]}) == 4
    # Image only toggles the image bit.
    assert build_license_flags({**base, "allowCommercialUse": ["Image"]}) == 2
    # Sell forces all commercial bits regardless of image listing.
    assert build_license_flags({**base, "allowCommercialUse": ["Sell"]}) == 30


def test_build_license_flags_parses_aggregate_string():
    source = {
        "allowNoCredit": True,
        "allowCommercialUse": "{Image,RentCivit,Rent}",
        "allowDerivatives": True,
        "allowDifferentLicense": False,
    }

    payload = resolve_license_payload(source)
    assert set(payload["allowCommercialUse"]) == {"Image", "RentCivit", "Rent"}

    flags = build_license_flags(source)
    expected_flags = (1 << 0) | (7 << 1) | (1 << 5)
    assert flags == expected_flags


def test_build_license_flags_parses_aggregate_inside_list():
    source = {
        "allowNoCredit": True,
        "allowCommercialUse": ["{Image,RentCivit,Rent}"],
        "allowDerivatives": True,
        "allowDifferentLicense": False,
    }

    payload = resolve_license_payload(source)
    assert set(payload["allowCommercialUse"]) == {"Image", "RentCivit", "Rent"}

    flags = build_license_flags(source)
    expected_flags = (1 << 0) | (7 << 1) | (1 << 5)
    assert flags == expected_flags

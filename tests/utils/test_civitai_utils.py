from py.utils.civitai_utils import (
    CommercialUseLevel,
    build_license_flags,
    resolve_license_info,
    resolve_license_payload,
)


def test_resolve_license_payload_defaults():
    payload, flags = resolve_license_info({})

    assert payload["allowNoCredit"] is True
    assert payload["allowDerivatives"] is True
    assert payload["allowDifferentLicense"] is True
    assert payload["allowCommercialUse"] == ["Sell"]
    assert flags == 57


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
    # Highest commercial level is SELL -> level 4 -> shifted by 1 == 8.
    assert flags == (CommercialUseLevel.SELL << 1)

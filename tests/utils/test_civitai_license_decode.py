"""Decoding tests for the cached license bitfield.

The persistent cache keeps license permissions as a single integer. When the
on-disk metadata is unreachable (offline drive) the modal renders its license
icons from that integer, so the decode must reproduce the exact CivitAI payload
shape ``build_license_flags`` encoded.
"""

import pytest

from py.utils.civitai_utils import (
    build_license_flags,
    decode_license_flags,
    resolve_license_payload,
)

PERMUTATIONS = [
    {
        "allowNoCredit": True,
        "allowCommercialUse": ["Sell"],
        "allowDerivatives": True,
        "allowDifferentLicense": True,
    },
    {
        "allowNoCredit": False,
        "allowCommercialUse": ["Image", "RentCivit", "Rent", "Sell"],
        "allowDerivatives": True,
        "allowDifferentLicense": True,
    },
    {
        "allowNoCredit": False,
        "allowCommercialUse": [],
        "allowDerivatives": False,
        "allowDifferentLicense": False,
    },
    {
        "allowNoCredit": True,
        "allowCommercialUse": ["Image", "Rent"],
        "allowDerivatives": False,
        "allowDifferentLicense": True,
    },
]


@pytest.mark.parametrize("payload", PERMUTATIONS)
def test_decode_round_trips_build_license_flags(payload):
    assert decode_license_flags(build_license_flags(payload)) == payload


def test_decode_maps_each_commercial_bit_to_its_civitai_value():
    base = {
        "allowNoCredit": False,
        "allowDerivatives": False,
        "allowDifferentLicense": False,
    }

    for value in ("Image", "RentCivit", "Rent", "Sell"):
        decoded = decode_license_flags(build_license_flags({**base, "allowCommercialUse": [value]}))
        assert decoded["allowCommercialUse"] == [value]


def test_decode_keeps_full_permission_combination():
    flags = build_license_flags(
        {
            "allowNoCredit": True,
            "allowCommercialUse": ["Image", "RentCivit", "Rent", "Sell"],
            "allowDerivatives": True,
            "allowDifferentLicense": True,
        }
    )

    assert flags == 127
    assert decode_license_flags(flags) == {
        "allowNoCredit": True,
        "allowCommercialUse": ["Image", "RentCivit", "Rent", "Sell"],
        "allowDerivatives": True,
        "allowDifferentLicense": True,
    }


def test_decode_falls_back_to_civitai_defaults_for_invalid_input():
    expected = decode_license_flags(build_license_flags({}))

    assert decode_license_flags(None) == expected
    assert decode_license_flags("not-a-number") == expected
    assert expected == resolve_license_payload({})

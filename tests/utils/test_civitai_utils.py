from py.utils.civitai_utils import (
    build_license_flags,
    extract_civitai_image_id,
    extract_civitai_model_url_parts,
    is_supported_civitai_page_host,
    normalize_civitai_download_url,
    resolve_license_info,
    resolve_license_payload,
)


def test_resolve_license_payload_defaults():
    payload, flags = resolve_license_info({})

    assert payload["allowNoCredit"] is True
    assert payload["allowDerivatives"] is True
    assert payload["allowDifferentLicense"] is True
    assert payload["allowCommercialUse"] == ["Sell"]
    # Default ["Sell"] only sets the Sell bit (16), plus NoCredit (1),
    # Derivatives (32) and DifferentLicense (64) = 113.
    assert flags == 113


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
    assert flags == 18


def test_build_license_flags_independent_values():
    base = {
        "allowNoCredit": False,
        "allowDerivatives": False,
        "allowDifferentLicense": False,
    }

    assert build_license_flags({**base, "allowCommercialUse": []}) == 0
    assert build_license_flags({**base, "allowCommercialUse": ["Rent"]}) == 8
    assert build_license_flags({**base, "allowCommercialUse": ["RentCivit"]}) == 4
    assert build_license_flags({**base, "allowCommercialUse": ["Image"]}) == 2
    assert build_license_flags({**base, "allowCommercialUse": ["Sell"]}) == 16


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


def test_supported_civitai_page_hosts_include_red():
    assert is_supported_civitai_page_host("civitai.com") is True
    assert is_supported_civitai_page_host("civitai.red") is True
    assert is_supported_civitai_page_host("www.civitai.com") is False
    assert is_supported_civitai_page_host("www.civitai.red") is False
    assert is_supported_civitai_page_host("example.com") is False


def test_extract_civitai_model_url_parts_supports_red():
    model_id, version_id = extract_civitai_model_url_parts(
        "https://civitai.red/models/65423/nijimecha-artstyle?modelVersionId=777"
    )

    assert model_id == "65423"
    assert version_id == "777"


def test_extract_civitai_model_url_parts_rejects_non_civitai_host():
    model_id, version_id = extract_civitai_model_url_parts(
        "https://example.com/models/65423?modelVersionId=777"
    )

    assert model_id is None
    assert version_id is None


def test_extract_civitai_image_id_supports_red():
    assert (
        extract_civitai_image_id("https://civitai.red/images/126920345")
        == "126920345"
    )


def test_extract_civitai_image_id_rejects_non_civitai_host():
    assert extract_civitai_image_id("https://example.com/images/126920345") is None


def test_normalize_civitai_download_url_rewrites_red_to_com():
    url = "https://civitai.red/api/download/models/2786889?type=Model&format=SafeTensor"

    assert (
        normalize_civitai_download_url(url)
        == "https://civitai.com/api/download/models/2786889?type=Model&format=SafeTensor"
    )


def test_normalize_civitai_download_url_keeps_non_download_red_urls():
    url = "https://civitai.red/models/65423/nijimecha-artstyle?modelVersionId=777"

    assert normalize_civitai_download_url(url) == url


def test_normalize_civitai_download_url_keeps_existing_com_urls():
    url = "https://civitai.com/api/download/models/2786889?type=Model&format=SafeTensor"

    assert normalize_civitai_download_url(url) == url

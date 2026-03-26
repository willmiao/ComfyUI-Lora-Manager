import pytest

from py.utils.constants import NSFW_LEVELS
from py.utils.preview_selection import resolve_mature_threshold, select_preview_media


def test_select_preview_returns_first_when_blur_disabled():
    images = [
        {"url": "nsfw", "type": "image", "nsfwLevel": 32},
        {"url": "safe", "type": "image", "nsfwLevel": 1},
    ]

    selected, level = select_preview_media(images, blur_mature_content=False)

    assert selected["url"] == "nsfw"
    assert level == 32


@pytest.mark.parametrize(
    ("threshold_name", "expected_url"),
    [
        ("PG13", "pg"),
        ("R", "pg13"),
        ("X", "r"),
        ("XXX", "x"),
    ],
)
def test_select_preview_respects_configurable_threshold(threshold_name, expected_url):
    images = [
        {"url": "xxx", "type": "image", "nsfwLevel": NSFW_LEVELS["XXX"]},
        {"url": "x", "type": "image", "nsfwLevel": NSFW_LEVELS["X"]},
        {"url": "r", "type": "image", "nsfwLevel": NSFW_LEVELS["R"]},
        {"url": "pg13", "type": "image", "nsfwLevel": NSFW_LEVELS["PG13"]},
        {"url": "pg", "type": "image", "nsfwLevel": NSFW_LEVELS["PG"]},
    ]

    selected, level = select_preview_media(
        images,
        blur_mature_content=True,
        mature_threshold=NSFW_LEVELS[threshold_name],
    )

    assert selected["url"] == expected_url
    assert level == next(item["nsfwLevel"] for item in images if item["url"] == expected_url)


def test_resolve_mature_threshold_falls_back_to_r_for_invalid_value():
    assert resolve_mature_threshold({"mature_blur_level": "invalid"}) == NSFW_LEVELS["R"]
    assert resolve_mature_threshold({}) == NSFW_LEVELS["R"]

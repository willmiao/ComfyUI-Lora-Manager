from py.utils.preview_selection import select_preview_media


def test_select_preview_prefers_safe_media_when_blurred():
    images = [
        {"url": "nsfw", "type": "image", "nsfwLevel": 8},
        {"url": "mid", "type": "image", "nsfwLevel": 4},
        {"url": "safe", "type": "image", "nsfwLevel": 1},
    ]

    selected, level = select_preview_media(images, blur_mature_content=True)

    assert selected["url"] == "safe"
    assert level == 1


def test_select_preview_returns_lowest_when_no_safe_media():
    images = [
        {"url": "x", "type": "image", "nsfwLevel": 16},
        {"url": "r", "type": "image", "nsfwLevel": 4},
        {"url": "xx", "type": "image", "nsfwLevel": 8},
    ]

    selected, level = select_preview_media(images, blur_mature_content=True)

    assert selected["url"] == "r"
    assert level == 4


def test_select_preview_returns_first_when_blur_disabled():
    images = [
        {"url": "nsfw", "type": "image", "nsfwLevel": 32},
        {"url": "safe", "type": "image", "nsfwLevel": 1},
    ]

    selected, level = select_preview_media(images, blur_mature_content=False)

    assert selected["url"] == "nsfw"
    assert level == 32

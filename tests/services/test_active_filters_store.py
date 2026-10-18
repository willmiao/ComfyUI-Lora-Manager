import pytest

from py.services.active_filters_store import (
    ActiveFiltersStore,
    active_filters_to_query_kwargs,
)


@pytest.fixture(autouse=True)
def reset_store():
    ActiveFiltersStore.reset_instance()
    yield
    ActiveFiltersStore.reset_instance()


def test_store_roundtrip():
    store = ActiveFiltersStore.get_instance()
    payload = {
        "activeFolder": "SD_XL",
        "recursiveSearch": False,
        "filters": {"baseModel": ["SDXL 1.0"], "tags": {"anime": "include"}},
    }
    store.set_filters("loras", payload)

    assert store.get_filters("loras") == payload
    assert store.get_filters("checkpoints") is None


def test_store_sanitizes_payload():
    store = ActiveFiltersStore.get_instance()
    store.set_filters(
        "loras",
        {
            "activeFolder": "anime",
            "recursiveSearch": True,
            "filters": {"baseModel": [], "unexpected": "dropped"},
            "extra": "dropped",
        },
    )

    stored = store.get_filters("loras")
    assert stored == {
        "activeFolder": "anime",
        "recursiveSearch": True,
        "filters": {"baseModel": []},
    }


def test_store_non_dict_filters_become_none():
    store = ActiveFiltersStore.get_instance()
    store.set_filters("loras", {"activeFolder": None, "filters": "garbage"})

    assert store.get_filters("loras")["filters"] is None


def test_store_clear():
    store = ActiveFiltersStore.get_instance()
    store.set_filters("loras", {"activeFolder": "x"})
    store.clear("loras")

    assert store.get_filters("loras") is None


def test_mapping_empty_payload():
    assert active_filters_to_query_kwargs(None) == {}
    assert active_filters_to_query_kwargs({}) == {}
    assert active_filters_to_query_kwargs({"activeFolder": None}) == {"recursive": True}


def test_mapping_folder():
    assert active_filters_to_query_kwargs(
        {"activeFolder": "SD_XL", "recursiveSearch": True}
    ) == {"folder": "SD_XL", "recursive": True}


def test_mapping_root_folder_non_recursive():
    # Root folder with recursion disabled matches only root-level files
    assert active_filters_to_query_kwargs(
        {"activeFolder": None, "recursiveSearch": False}
    ) == {"folder": "", "recursive": False}


def test_mapping_legacy_null_string_folder():
    assert active_filters_to_query_kwargs(
        {"activeFolder": "null", "recursiveSearch": True}
    ) == {"recursive": True}


def test_mapping_full_filters():
    kwargs = active_filters_to_query_kwargs(
        {
            "activeFolder": "anime",
            "recursiveSearch": True,
            "filters": {
                "baseModel": ["SDXL 1.0", "Pony"],
                "tags": {"anime": "include", "3d": "exclude", "junk": "ignored"},
                "autoTags": {"cute": "include"},
                "modelTypes": ["LoRA"],
                "tagLogic": "all",
                "license": {"noCredit": "include", "allowSelling": "exclude"},
            },
        }
    )

    assert kwargs == {
        "folder": "anime",
        "recursive": True,
        "base_models": ["SDXL 1.0", "Pony"],
        "tags": {"anime": "include", "3d": "exclude"},
        "auto_tags": {"cute": "include"},
        "model_types": ["LoRA"],
        "tag_logic": "all",
        "credit_required": False,
        "allow_selling_generated_content": False,
    }


def test_mapping_license_exclude_variants():
    kwargs = active_filters_to_query_kwargs(
        {
            "filters": {
                "license": {"noCredit": "exclude", "allowSelling": "include"},
            },
        }
    )

    assert kwargs["credit_required"] is True
    assert kwargs["allow_selling_generated_content"] is True

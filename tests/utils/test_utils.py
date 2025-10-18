import pytest

from py.services.settings_manager import SettingsManager, get_settings_manager
from py.utils.utils import (
    calculate_recipe_fingerprint,
    calculate_relative_path_for_model,
    sanitize_folder_name,
)


@pytest.fixture
def isolated_settings(monkeypatch):
    manager = get_settings_manager()
    default_settings = manager._get_default_settings()
    default_settings.update(
        {
            "download_path_templates": {
                "lora": "{base_model}/{first_tag}",
                "checkpoint": "{base_model}/{first_tag}",
                "embedding": "{base_model}/{first_tag}",
            },
            "base_model_path_mappings": {},
        }
    )
    monkeypatch.setattr(manager, "settings", default_settings)
    monkeypatch.setattr(SettingsManager, "_save_settings", lambda self: None)
    return default_settings


def test_calculate_relative_path_for_embedding_replaces_spaces(isolated_settings):
    model_data = {
        "base_model": "Base Model",
        "tags": ["tag with space"],
        "civitai": {"id": 1, "creator": {"username": "Author Name"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "embedding")

    assert relative_path == "Base_Model/tag_with_space"


def test_calculate_relative_path_for_model_uses_mappings_and_defaults(isolated_settings):
    isolated_settings["download_path_templates"]["lora"] = "{base_model}/{first_tag}/{author}"
    isolated_settings["base_model_path_mappings"] = {"SDXL": "SDXL-mapped"}

    model_data = {
        "base_model": "SDXL",
        "tags": [],
        "civitai": {"id": 12, "creator": {"username": "Creator"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "SDXL-mapped/no tags/Creator"


def test_calculate_relative_path_supports_model_and_version(isolated_settings):
    isolated_settings["download_path_templates"]["lora"] = "{model_name}/{version_name}"

    model_data = {
        "model_name": "Fancy Model",
        "base_model": "SDXL",
        "tags": ["tag"],
        "civitai": {"id": 1, "name": "Version One", "creator": {"username": "Creator"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "Fancy Model/Version One"


def test_calculate_relative_path_sanitizes_model_and_version_names(isolated_settings):
    isolated_settings["download_path_templates"]["lora"] = "{model_name}/{version_name}"

    model_data = {
        "model_name": "Fancy:Model*",
        "base_model": "SDXL",
        "tags": ["tag"],
        "civitai": {"id": 1, "name": "Version:One?", "creator": {"username": "Creator"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "Fancy_Model/Version_One"


def test_calculate_recipe_fingerprint_filters_and_sorts():
    loras = [
        {"hash": "ABC", "strength": 0.1234},
        {"hash": "", "isDeleted": True, "modelVersionId": 42, "strength": 0.5},
        {"hash": "def", "weight": 0.345},
        {"hash": "skip", "exclude": True, "strength": 0.9},
        {"hash": "", "strength": 0.1},
    ]

    fingerprint = calculate_recipe_fingerprint(loras)

    assert fingerprint == "42:0.5|abc:0.12|def:0.34"


def test_calculate_recipe_fingerprint_empty_input():
    assert calculate_recipe_fingerprint([]) == ""


@pytest.mark.parametrize(
    "original, expected",
    [
        ("ValidName", "ValidName"),
        ("Invalid:Name", "Invalid_Name"),
        ("Trailing. ", "Trailing"),
        ("", ""),
        (":::", "unnamed"),
    ],
)
def test_sanitize_folder_name(original, expected):
    assert sanitize_folder_name(original) == expected

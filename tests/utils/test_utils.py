import pytest

from py.services.settings_manager import SettingsManager, get_settings_manager
from py.services.service_registry import ServiceRegistry
from py.utils.utils import (
    calculate_recipe_fingerprint,
    calculate_relative_path_for_model,
    get_lora_info,
    get_lora_info_absolute,
    sanitize_folder_name,
)


class _FakeCache:
    def __init__(self, items):
        self.raw_data = list(items)


class _FakeScanner:
    def __init__(self, items):
        self._cache = _FakeCache(items)

    async def get_cached_data(self):
        return self._cache


@pytest.fixture
def mock_lora_scanner(monkeypatch):
    def _setup(items):
        scanner = _FakeScanner(items)

        async def get_scanner():
            return scanner

        monkeypatch.setattr(ServiceRegistry, "get_lora_scanner", get_scanner)
        return scanner

    return _setup


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


def test_calculate_relative_path_sanitizes_leading_slash(isolated_settings):
    """Test that empty base_model does NOT produce a leading slash in the path."""
    isolated_settings["download_path_templates"]["lora"] = "{base_model}/{first_tag}"

    model_data = {
        "base_model": "",
        "tags": [],
        "civitai": {"id": 1, "creator": {"username": "Author"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert not relative_path.startswith("/")
    assert relative_path == "no tags"


def test_calculate_relative_path_sanitizes_double_slashes(isolated_settings):
    """Test that empty substitutions don't produce double slashes."""
    isolated_settings["download_path_templates"]["lora"] = "{base_model}/{first_tag}/{author}"

    model_data = {
        "base_model": "",
        "tags": [],
        "civitai": {"id": 1, "creator": {"username": "Author"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert "//" not in relative_path
    assert relative_path == "no tags/Author"


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


def test_get_lora_info_absolute_bare_name(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL", "file_path": "/models/Lora/SDXL/mylora.safetensors", "civitai": {"trainedWords": ["trigger1"]}},
    ])

    path, triggers = get_lora_info_absolute("mylora")

    assert path == "/models/Lora/SDXL/mylora.safetensors"
    assert triggers == ["trigger1"]


def test_get_lora_info_absolute_with_path(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL/Styles", "file_path": "/models/Lora/SDXL/Styles/mylora.safetensors", "civitai": {"trainedWords": ["artistic"]}},
        {"file_name": "other", "folder": "", "file_path": "/models/Lora/other.safetensors", "civitai": {}},
    ])

    path, triggers = get_lora_info_absolute("SDXL/Styles/mylora")

    assert path == "/models/Lora/SDXL/Styles/mylora.safetensors"
    assert triggers == ["artistic"]


def test_get_lora_info_absolute_path_fallback_to_basename(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "RenamedFolder", "file_path": "/models/Lora/RenamedFolder/mylora.safetensors", "civitai": {"trainedWords": ["trigger1"]}},
    ])

    path, triggers = get_lora_info_absolute("OldFolder/mylora")

    assert path == "/models/Lora/RenamedFolder/mylora.safetensors"
    assert triggers == ["trigger1"]


def test_get_lora_info_absolute_prefers_folder_match(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "V1", "file_path": "/models/Lora/V1/mylora.safetensors", "civitai": {"trainedWords": ["v1"]}},
        {"file_name": "mylora", "folder": "V2", "file_path": "/models/Lora/V2/mylora.safetensors", "civitai": {"trainedWords": ["v2"]}},
    ])

    path, triggers = get_lora_info_absolute("V2/mylora")

    assert path == "/models/Lora/V2/mylora.safetensors"
    assert triggers == ["v2"]


def test_get_lora_info_absolute_no_folder_in_cache_no_path_in_name(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "", "file_path": "/models/Lora/mylora.safetensors", "civitai": {}},
    ])

    path, triggers = get_lora_info_absolute("mylora")

    assert path == "/models/Lora/mylora.safetensors"
    assert triggers == []


def test_get_lora_info_absolute_strips_extension(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL", "file_path": "/models/Lora/SDXL/mylora.safetensors", "civitai": {"trainedWords": ["hello"]}},
    ])

    path, triggers = get_lora_info_absolute("SDXL/mylora.safetensors")

    assert path == "/models/Lora/SDXL/mylora.safetensors"
    assert triggers == ["hello"]


def test_get_lora_info_absolute_not_found_returns_original(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL", "file_path": "/models/Lora/SDXL/mylora.safetensors", "civitai": {}},
    ])

    path, triggers = get_lora_info_absolute("nonexistent")

    assert path == "nonexistent"
    assert triggers == []


def test_get_lora_info_bare_name(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL", "file_path": "/models/Lora/SDXL/mylora.safetensors", "civitai": {"trainedWords": ["trigger1"]}},
    ])

    path, triggers = get_lora_info("mylora")

    assert triggers == ["trigger1"]


def test_get_lora_info_with_path(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL/Styles", "file_path": "/models/Lora/SDXL/Styles/mylora.safetensors", "civitai": {"trainedWords": ["artistic"]}},
        {"file_name": "other", "folder": "", "file_path": "/models/Lora/other.safetensors", "civitai": {}},
    ])

    path, triggers = get_lora_info("SDXL/Styles/mylora")

    assert triggers == ["artistic"]


def test_get_lora_info_not_found_returns_original(mock_lora_scanner):
    mock_lora_scanner([
        {"file_name": "mylora", "folder": "SDXL", "file_path": "/models/Lora/SDXL/mylora.safetensors", "civitai": {}},
    ])

    path, triggers = get_lora_info("nonexistent")

    assert path == "nonexistent"
    assert triggers == []

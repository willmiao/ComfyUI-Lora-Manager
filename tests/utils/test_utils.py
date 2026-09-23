import pytest

from py.services.settings_manager import SettingsManager, get_settings_manager
from py.services.service_registry import ServiceRegistry
from py.utils.constants import (
    MAX_FILENAME_STEM_LENGTH,
    MAX_FOLDER_NAME_LENGTH,
    MAX_PATH_TAG_LENGTH,
)
from py.utils.utils import (
    calculate_filename_for_model,
    calculate_recipe_fingerprint,
    calculate_relative_path_for_model,
    get_lora_info,
    get_lora_info_absolute,
    sanitize_folder_name,
)


# Real CivitAI data for the model reported in issue #1119: the uploader dumped
# a whole keyword list into a single tag.
KEYWORD_DUMP_TAG = (
    "lora, character, rosie, irish, redhead, auburn, freckles, green eyes, "
    "curly hair, woman, female, photorealistic, realistic, krea2, dark beast, "
    "kreativity, nsfw, nude, portrait, face"
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


def test_calculate_relative_path_ignores_keyword_dump_tag(isolated_settings):
    """A tag holding a whole keyword list must not become a folder name (#1119)."""
    model_data = {"base_model": "Krea 2", "tags": [KEYWORD_DUMP_TAG]}

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "Krea 2/no tags"


def test_calculate_relative_path_uses_next_usable_tag(isolated_settings):
    """Unusable tags are skipped instead of hijacking the folder name (#1119)."""
    model_data = {"base_model": "Krea 2", "tags": [KEYWORD_DUMP_TAG, "portrait"]}

    assert calculate_relative_path_for_model(model_data, "lora") == "Krea 2/portrait"


def test_calculate_relative_path_ignores_civitai_meta_tag(isolated_settings):
    """Civitai's "base model" label is not content, so it is not a folder."""
    model_data = {"base_model": "Krea 2", "tags": ["base model"]}

    assert calculate_relative_path_for_model(model_data, "lora") == "Krea 2/no tags"


def test_calculate_relative_path_ignores_full_1119_tag_list(isolated_settings):
    """The reported model carries only a keyword dump and the meta label."""
    model_data = {"base_model": "Krea 2", "tags": [KEYWORD_DUMP_TAG, "base model"]}

    assert calculate_relative_path_for_model(model_data, "lora") == "Krea 2/no tags"


def test_calculate_relative_path_sanitizes_tag_segment(isolated_settings):
    """A tag with path separators must not create nested folders."""
    model_data = {"base_model": "SDXL", "tags": ["a/b:c"]}

    assert calculate_relative_path_for_model(model_data, "lora") == "SDXL/a_b_c"


def test_calculate_relative_path_caps_tag_segment(isolated_settings):
    """A long configured priority tag is truncated to the tag length budget."""
    long_tag = "y" * 80
    isolated_settings["priority_tags"] = {"lora": long_tag}

    model_data = {"base_model": "SDXL", "tags": [long_tag]}

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "SDXL/" + "y" * MAX_PATH_TAG_LENGTH


def test_calculate_relative_path_keeps_tag_within_budget(isolated_settings):
    model_data = {"base_model": "SDXL", "tags": ["t" * 40]}

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == "SDXL/" + "t" * 40


def test_calculate_relative_path_caps_model_and_version_names(isolated_settings):
    isolated_settings["download_path_templates"]["lora"] = "{model_name}/{version_name}"

    model_data = {
        "model_name": "m" * 300,
        "base_model": "SDXL",
        "tags": [],
        "civitai": {"id": 1, "name": "v" * 300, "creator": {"username": "Creator"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "lora")

    assert relative_path == (
        "m" * MAX_FOLDER_NAME_LENGTH + "/" + "v" * MAX_FOLDER_NAME_LENGTH
    )


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


def _set_filename_templates(isolated_settings, template, model_types=("lora", "checkpoint", "embedding")):
    isolated_settings["download_filename_templates"] = {
        model_type: template for model_type in model_types
    }


def test_calculate_filename_returns_empty_without_template(isolated_settings):
    model_data = {"model_name": "Model", "file_path": "/models/V1.safetensors"}

    assert calculate_filename_for_model(model_data, "lora") == ""


def test_calculate_filename_substitutes_all_placeholders(isolated_settings):
    _set_filename_templates(
        isolated_settings,
        "{base_model}-{model_name}-{version_name}-{author}-{first_tag}-{hash_short}-{original_name}",
    )

    model_data = {
        "model_name": "My Model",
        "base_model": "SDXL",
        "tags": ["Style"],
        "sha256": "ABCDEF0123456789",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1, "name": "v3", "creator": {"username": "Author"}},
    }

    result = calculate_filename_for_model(model_data, "lora")

    assert result == "SDXL-My Model-v3-Author-style-abcdef0123-V1"


def test_calculate_filename_hash_short_empty_when_unknown(isolated_settings):
    _set_filename_templates(isolated_settings, "{model_name}-{hash_short}")

    model_data = {
        "model_name": "My Model",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    # Missing hash leaves an empty segment; the dangling separator collapses.
    assert calculate_filename_for_model(model_data, "lora") == "My Model"


def test_calculate_filename_missing_metadata_produces_empty_segments(isolated_settings):
    _set_filename_templates(isolated_settings, "{base_model}-{model_name}")

    model_data = {
        "model_name": "My Model",
        "base_model": "",
        "tags": [],
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    assert calculate_filename_for_model(model_data, "lora") == "My Model"


def test_calculate_filename_rejects_path_separators(isolated_settings):
    _set_filename_templates(isolated_settings, "{base_model}/{model_name}")

    model_data = {
        "model_name": "My Model",
        "base_model": "SDXL",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    assert calculate_filename_for_model(model_data, "lora") == ""

    _set_filename_templates(isolated_settings, "{base_model}\\{model_name}")
    assert calculate_filename_for_model(model_data, "lora") == ""


def test_calculate_filename_strips_illegal_characters(isolated_settings):
    _set_filename_templates(isolated_settings, '{model_name}:"custom"')

    model_data = {
        "model_name": "My:Model*",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    result = calculate_filename_for_model(model_data, "lora")

    assert result == "My_Modelcustom"


def test_calculate_filename_empty_result_returns_empty(isolated_settings):
    _set_filename_templates(isolated_settings, "{base_model}-{first_tag}")

    model_data = {
        "base_model": "",
        "tags": [],
        "file_path": "/models/V1.safetensors",
    }

    assert calculate_filename_for_model(model_data, "lora") == ""


def test_calculate_filename_uses_base_model_mapping(isolated_settings):
    _set_filename_templates(isolated_settings, "{base_model}-{model_name}")
    isolated_settings["base_model_path_mappings"] = {"SDXL": "sdxl-mapped"}

    model_data = {
        "model_name": "Model",
        "base_model": "SDXL",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    assert calculate_filename_for_model(model_data, "lora") == "sdxl-mapped-Model"


def test_calculate_filename_embedding_replaces_spaces(isolated_settings):
    _set_filename_templates(isolated_settings, "{base_model} {model_name}")

    model_data = {
        "model_name": "My Model",
        "base_model": "Base Model",
        "file_path": "/models/V1.safetensors",
        "civitai": {"id": 1},
    }

    assert calculate_filename_for_model(model_data, "embedding") == "Base_Model_My_Model"


def test_calculate_filename_original_name_falls_back_to_file_name(isolated_settings):
    _set_filename_templates(isolated_settings, "{original_name}-{hash_short}")

    model_data = {
        "file_name": "legacy-name",
        "sha256": "0123456789abcdef",
    }

    assert calculate_filename_for_model(model_data, "lora") == "legacy-name-0123456789"


def test_calculate_filename_drops_keyword_dump_tag(isolated_settings):
    """The keyword-dump tag collapses instead of filling the filename (#1119)."""
    _set_filename_templates(isolated_settings, "{base_model}-{first_tag}")

    model_data = {
        "base_model": "Krea 2",
        "tags": [KEYWORD_DUMP_TAG],
        "file_path": "/models/V1.safetensors",
    }

    assert calculate_filename_for_model(model_data, "lora") == "Krea 2"


def test_calculate_filename_caps_rendered_stem(isolated_settings):
    _set_filename_templates(isolated_settings, "{model_name}")

    model_data = {
        "model_name": "m" * 400,
        "file_path": "/models/V1.safetensors",
    }

    result = calculate_filename_for_model(model_data, "lora")

    assert len(result) == MAX_FILENAME_STEM_LENGTH


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


def test_sanitize_folder_name_without_max_length_is_unbounded():
    assert sanitize_folder_name("x" * 300) == "x" * 300


@pytest.mark.parametrize(
    "original, max_length, expected",
    [
        ("abcdefghij", 4, "abcd"),
        # Re-trim separators and spaces exposed by the cut.
        ("abc...defg", 4, "abc"),
        ("abcdefg hij", 8, "abcdefg"),
        # Shorter than the cap is returned untouched.
        ("short", 10, "short"),
        # A cut that leaves only separators falls back to "unnamed".
        ("...abcdef", 3, "unnamed"),
    ],
)
def test_sanitize_folder_name_truncates_to_max_length(original, max_length, expected):
    assert sanitize_folder_name(original, max_length=max_length) == expected


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

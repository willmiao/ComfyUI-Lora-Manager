import pytest

from py.services.settings_manager import settings
from py.utils.utils import calculate_relative_path_for_model


@pytest.fixture
def isolated_settings(monkeypatch):
    default_settings = settings._get_default_settings()
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
    monkeypatch.setattr(settings, "settings", default_settings)
    monkeypatch.setattr(type(settings), "_save_settings", lambda self: None)
    return default_settings


def test_calculate_relative_path_for_embedding_replaces_spaces(isolated_settings):
    model_data = {
        "base_model": "Base Model",
        "tags": ["tag with space"],
        "civitai": {"id": 1, "creator": {"username": "Author Name"}},
    }

    relative_path = calculate_relative_path_for_model(model_data, "embedding")

    assert relative_path == "Base_Model/tag_with_space"

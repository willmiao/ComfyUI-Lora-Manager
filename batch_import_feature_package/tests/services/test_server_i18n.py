from py.services.server_i18n import ServerI18nManager


def _build_manager(translations):
    manager = ServerI18nManager()
    manager.translations = translations
    manager.current_locale = "en"
    return manager


def test_get_translation_accepts_legacy_default_positional_argument():
    manager = _build_manager({"en": {"recipes": {}}})
    value = manager.get_translation(
        "recipes.controls.batchImport.title",
        {},
        "Batch Import Recipes",
    )
    assert value == "Batch Import Recipes"


def test_get_translation_uses_english_fallback_before_default():
    manager = _build_manager(
        {
            "en": {"recipes": {"title": "Recipes"}},
            "fr": {"recipes": {}},
        }
    )
    manager.set_locale("fr")
    value = manager.get_translation("recipes.title", {}, "Default Title")
    assert value == "Recipes"


def test_get_translation_supports_string_second_argument_as_default():
    manager = _build_manager({"en": {"recipes": {}}})
    value = manager.get_translation("recipes.missing", "Fallback Title")
    assert value == "Fallback Title"

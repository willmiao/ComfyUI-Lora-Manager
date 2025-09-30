"""Regression tests for localization data and usage.

These tests validate three key aspects of the localisation setup:

* Every locale file is valid JSON and contains the expected sections.
* All locales expose the same translation keys as the English reference.
* Static JavaScript/HTML sources only reference available translation keys.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Set

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
LOCALES_DIR = ROOT_DIR / "locales"
STATIC_JS_DIR = ROOT_DIR / "static" / "js"
TEMPLATES_DIR = ROOT_DIR / "templates"

EXPECTED_LOCALES = (
    "en",
    "zh-CN",
    "zh-TW",
    "ja",
    "ru",
    "de",
    "fr",
    "es",
    "ko",
    "he",
)

REQUIRED_SECTIONS = {"common", "header", "loras", "recipes", "modals"}

SINGLE_WORD_TRANSLATION_KEYS = {
    "loading",
    "error",
    "success",
    "warning",
    "info",
    "cancel",
    "save",
    "delete",
}

FALSE_POSITIVES = {
    "checkpoint",
    "civitai_api_key",
    "div",
    "embedding",
    "lora",
    "show_only_sfw",
    "model",
    "type",
    "name",
    "value",
    "id",
    "class",
    "style",
    "src",
    "href",
    "data",
    "width",
    "height",
    "size",
    "format",
    "version",
    "url",
    "path",
    "file",
    "folder",
    "image",
    "text",
    "number",
    "boolean",
    "array",
    "object",
    "non.existent.key",
}

SPECIAL_UI_HELPER_KEYS = {
    "uiHelpers.workflow.loraAdded",
    "uiHelpers.workflow.loraReplaced",
    "uiHelpers.workflow.loraFailedToSend",
    "uiHelpers.workflow.recipeAdded",
    "uiHelpers.workflow.recipeReplaced",
    "uiHelpers.workflow.recipeFailedToSend",
}

JS_TRANSLATION_PATTERNS = (
    r"\btranslate\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]",
    r"\bshowToast\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]",
    r"\bt\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"]",
)

HTML_TRANSLATION_PATTERN = (
    r"(?:\{\{|\{%)[^}]*\bt\s*\(\s*['\"]([a-zA-Z0-9._-]+)['\"][^}]*(?:\}\}|%\})"
)


@pytest.fixture(scope="module")
def loaded_locales() -> Dict[str, dict]:
    """Load locale JSON once per test module."""
    locales: Dict[str, dict] = {}

    for locale in EXPECTED_LOCALES:
        path = LOCALES_DIR / f"{locale}.json"
        if not path.exists():
            pytest.fail(f"Locale file {path.name} is missing", pytrace=False)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - explicit failure message
            pytest.fail(f"Locale file {path.name} contains invalid JSON: {exc}", pytrace=False)

        if not isinstance(data, dict):
            pytest.fail(
                f"Locale file {path.name} must contain a JSON object at the top level",
                pytrace=False,
            )

        locales[locale] = data

    return locales


@pytest.fixture(scope="module")
def english_translation_keys(loaded_locales: Dict[str, dict]) -> Set[str]:
    return collect_translation_keys(loaded_locales["en"])


@pytest.fixture(scope="module")
def static_code_translation_keys() -> Set[str]:
    return gather_static_translation_keys()


def collect_translation_keys(data: dict, prefix: str = "") -> Set[str]:
    """Recursively collect translation keys from a locale dictionary."""
    keys: Set[str] = set()

    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys.update(collect_translation_keys(value, full_key))
        else:
            keys.add(full_key)

    return keys


def gather_static_translation_keys() -> Set[str]:
    """Collect translation keys referenced in static JavaScript and HTML templates."""
    keys: Set[str] = set()

    if STATIC_JS_DIR.exists():
        for file_path in STATIC_JS_DIR.rglob("*.js"):
            keys.update(filter_translation_keys(extract_i18n_keys_from_js(file_path)))

    if TEMPLATES_DIR.exists():
        for file_path in TEMPLATES_DIR.rglob("*.html"):
            keys.update(filter_translation_keys(extract_i18n_keys_from_html(file_path)))

    keys.update(SPECIAL_UI_HELPER_KEYS)

    return keys


def filter_translation_keys(raw_keys: Iterable[str]) -> Set[str]:
    """Filter out obvious false positives and non-translation identifiers."""
    filtered: Set[str] = set()
    for key in raw_keys:
        if key in FALSE_POSITIVES:
            continue
        if "." not in key and key not in SINGLE_WORD_TRANSLATION_KEYS:
            continue
        filtered.add(key)
    return filtered


def extract_i18n_keys_from_js(file_path: Path) -> Set[str]:
    """Extract translation keys from JavaScript sources."""
    content = file_path.read_text(encoding="utf-8")
    # Remove single-line and multi-line comments to avoid false positives.
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    matches: Set[str] = set()
    for pattern in JS_TRANSLATION_PATTERNS:
        matches.update(re.findall(pattern, content))
    return matches


def extract_i18n_keys_from_html(file_path: Path) -> Set[str]:
    """Extract translation keys from HTML templates."""
    content = file_path.read_text(encoding="utf-8")
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

    matches: Set[str] = set(re.findall(HTML_TRANSLATION_PATTERN, content))

    # Inspect inline script tags as JavaScript.
    for script_body in re.findall(r"<script[^>]*>(.*?)</script>", content, flags=re.DOTALL):
        for pattern in JS_TRANSLATION_PATTERNS:
            matches.update(re.findall(pattern, script_body))

    return matches


@pytest.mark.parametrize("locale", EXPECTED_LOCALES)
def test_locale_files_have_expected_structure(locale: str, loaded_locales: Dict[str, dict]) -> None:
    """Every locale must contain the required sections."""
    data = loaded_locales[locale]
    missing_sections = sorted(REQUIRED_SECTIONS - data.keys())
    assert not missing_sections, f"{locale} locale is missing sections: {missing_sections}"


@pytest.mark.parametrize("locale", EXPECTED_LOCALES[1:])
def test_locale_keys_match_english(
    locale: str, loaded_locales: Dict[str, dict], english_translation_keys: Set[str]
) -> None:
    """Locales must expose the same translation keys as English."""
    locale_keys = collect_translation_keys(loaded_locales[locale])

    missing_keys = sorted(english_translation_keys - locale_keys)
    extra_keys = sorted(locale_keys - english_translation_keys)

    assert not missing_keys, (
        f"{locale} is missing translation keys: {missing_keys[:10]}"
        + ("..." if len(missing_keys) > 10 else "")
    )
    assert not extra_keys, (
        f"{locale} defines unexpected translation keys: {extra_keys[:10]}"
        + ("..." if len(extra_keys) > 10 else "")
    )


def test_static_sources_only_use_existing_translations(
    english_translation_keys: Set[str], static_code_translation_keys: Set[str]
) -> None:
    """Static code must not reference unknown translation keys."""
    missing_keys = sorted(static_code_translation_keys - english_translation_keys)
    assert not missing_keys, (
        "Static sources reference missing translation keys: "
        f"{missing_keys[:20]}" + ("..." if len(missing_keys) > 20 else "")
    )

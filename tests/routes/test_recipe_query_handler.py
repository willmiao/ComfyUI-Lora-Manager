import json
import logging
from types import SimpleNamespace

import pytest

from py.routes.handlers.recipe_handlers import RecipeQueryHandler
from py.services.recipe_scanner import UNKNOWN_BASE_MODEL_FILTER


async def _noop():
    return None


@pytest.mark.asyncio
async def test_recipe_query_handler_base_models_limit_zero_returns_all():
    cache = SimpleNamespace(
        raw_data=[
            {"base_model": "SDXL"},
            {"base_model": "LTXV 2.3"},
            {"base_model": "SDXL"},
        ]
    )
    scanner = SimpleNamespace(get_cached_data=lambda: None)

    async def get_cached_data():
        return cache

    scanner.get_cached_data = get_cached_data

    handler = RecipeQueryHandler(
        ensure_dependencies_ready=_noop,
        recipe_scanner_getter=lambda: scanner,
        format_recipe_file_url=lambda value: value,
        logger=logging.getLogger(__name__),
    )

    response = await handler.get_base_models(
        SimpleNamespace(query={"limit": "0"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

    assert payload["success"] is True
    assert payload["base_models"] == [
        {"name": "SDXL", "count": 2},
        {"name": "LTXV 2.3", "count": 1},
    ]


@pytest.mark.asyncio
async def test_recipe_query_handler_base_models_includes_unknown_bucket():
    cache = SimpleNamespace(
        raw_data=[
            {"base_model": "SDXL"},
            {"base_model": None},
            {"base_model": ""},
        ]
    )
    scanner = SimpleNamespace(get_cached_data=lambda: None)

    async def get_cached_data():
        return cache

    scanner.get_cached_data = get_cached_data

    handler = RecipeQueryHandler(
        ensure_dependencies_ready=_noop,
        recipe_scanner_getter=lambda: scanner,
        format_recipe_file_url=lambda value: value,
        logger=logging.getLogger(__name__),
    )

    response = await handler.get_base_models(
        SimpleNamespace(query={"limit": "0"})  # pyright: ignore[reportArgumentType]
    )
    text = response.text
    assert text is not None
    payload = json.loads(text)

    assert payload["success"] is True
    # Unknown bucket carries a dedicated marker so the UI can show "Unknown"
    # without colliding with real base model strings.
    assert payload["base_models"] == [
        {"name": "Unknown", "value": UNKNOWN_BASE_MODEL_FILTER, "count": 2},
        {"name": "SDXL", "count": 1},
    ]

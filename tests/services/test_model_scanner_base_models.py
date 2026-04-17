from types import SimpleNamespace

import pytest

from py.services.model_scanner import ModelScanner


class DummyScanner:
    def __init__(self, raw_data):
        self._cache = SimpleNamespace(raw_data=raw_data)

    async def get_cached_data(self):
        return self._cache


@pytest.mark.asyncio
async def test_get_base_models_limit_zero_returns_all_sorted():
    scanner = DummyScanner(
        [
            {"base_model": "SDXL"},
            {"base_model": "LTXV 2.3"},
            {"base_model": "SDXL"},
            {"base_model": ""},
            {},
        ]
    )

    result = await ModelScanner.get_base_models(scanner, limit=0)

    assert result == [
        {"name": "SDXL", "count": 2},
        {"name": "LTXV 2.3", "count": 1},
    ]


@pytest.mark.asyncio
async def test_get_base_models_positive_limit_still_truncates():
    scanner = DummyScanner(
        [
            {"base_model": "SDXL"},
            {"base_model": "LTXV 2.3"},
            {"base_model": "Flux.1 D"},
            {"base_model": "SDXL"},
        ]
    )

    result = await ModelScanner.get_base_models(scanner, limit=2)

    assert result == [
        {"name": "SDXL", "count": 2},
        {"name": "LTXV 2.3", "count": 1},
    ]

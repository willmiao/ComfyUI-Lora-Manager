import json
from unittest.mock import MagicMock

import pytest

from py.services.wildcard_activation_service import WildcardActivationService
from py.services.wildcard_model_service import WildcardModelService


SEARCH_OPTIONS = {
    "filename": False,
    "modelname": False,
    "tags": False,
    "creator": False,
    "wildcard_keys": True,
}


def write_activation(path, file_path, *, active=True):
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "resources": {
                    file_path: {
                        "file_path": file_path,
                        "active": active,
                        "namespace": "palette",
                        "aliases": {"warm": "warm colors"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def make_resource():
    return {
        "file_path": "/library/colors.txt",
        "file_name": "colors",
        "model_name": "Colors",
        "entries": [{"key": "warm", "values_count": 2}],
    }


@pytest.mark.asyncio
async def test_search_matches_source_and_active_effective_keys(tmp_path, monkeypatch):
    activation_path = tmp_path / "activations.json"
    resource = make_resource()
    write_activation(activation_path, resource["file_path"])
    activation_service = WildcardActivationService(str(activation_path))
    service = WildcardModelService(MagicMock(), activation_service=activation_service)

    original_load = activation_service._load
    load_calls = 0

    def counted_load():
        nonlocal load_calls
        load_calls += 1
        return original_load()

    monkeypatch.setattr(activation_service, "_load", counted_load)
    result = await service._apply_search_filters(
        [resource], "__palette/warm colors__", True, SEARCH_OPTIONS
    )

    assert [item["file_path"] for item in result] == [resource["file_path"]]
    assert result[0]["entries"][0]["effective_key"] == "palette/warm colors"
    assert "effective_key" not in resource["entries"][0]
    assert load_calls == 1

    source_result = await service._apply_search_filters(
        [resource], "warm", True, SEARCH_OPTIONS
    )
    assert len(source_result) == 1


@pytest.mark.asyncio
async def test_inactive_resource_does_not_match_saved_alias(tmp_path):
    activation_path = tmp_path / "activations.json"
    resource = make_resource()
    write_activation(activation_path, resource["file_path"], active=False)
    service = WildcardModelService(
        MagicMock(),
        activation_service=WildcardActivationService(str(activation_path)),
    )

    alias_result = await service._apply_search_filters(
        [resource], "palette", True, SEARCH_OPTIONS
    )
    source_result = await service._apply_search_filters(
        [resource], "warm", True, SEARCH_OPTIONS
    )

    assert alias_result == []
    assert len(source_result) == 1


@pytest.mark.asyncio
async def test_wildcard_service_ignores_fuzzy_matching(tmp_path):
    resource = make_resource()
    service = WildcardModelService(
        MagicMock(),
        activation_service=WildcardActivationService(str(tmp_path / "missing.json")),
    )

    result = await service._apply_search_filters(
        [resource], "pallete", True, SEARCH_OPTIONS
    )

    assert result == []

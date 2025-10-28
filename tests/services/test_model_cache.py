import pytest

from py.services.model_cache import ModelCache


@pytest.mark.asyncio
async def test_model_cache_tracks_versions_by_model_id():
    item_one = {
        'file_path': '/models/a.safetensors',
        'file_name': 'model-a-v1',
        'folder': '',
        'civitai': {'id': 101, 'modelId': 1, 'name': 'Alpha'},
    }
    item_two = {
        'file_path': '/models/a_v2.safetensors',
        'file_name': 'model-a-v2',
        'folder': '',
        'civitai': {'id': 102, 'modelId': 1, 'name': 'Beta'},
    }
    item_three = {
        'file_path': '/models/b.safetensors',
        'file_name': 'model-b',
        'folder': '',
        'civitai': {'id': 201, 'modelId': 2, 'name': 'Gamma'},
    }

    cache = ModelCache(
        raw_data=[item_one, item_two, item_three],
        folders=[],
        name_display_mode='model_name',
    )

    versions = cache.get_versions_by_model_id(1)
    assert versions == [
        {'versionId': 101, 'name': 'Alpha', 'fileName': 'model-a-v1'},
        {'versionId': 102, 'name': 'Beta', 'fileName': 'model-a-v2'},
    ]

    # Returned descriptors should not allow external mutation of the cache index
    versions[0]['name'] = 'mutated'
    assert cache.model_id_index[1][0]['name'] == 'Alpha'

    # Removing entries updates both indexes
    cache.remove_from_version_index(item_one)
    assert cache.get_versions_by_model_id(1) == [
        {'versionId': 102, 'name': 'Beta', 'fileName': 'model-a-v2'},
    ]

    cache.remove_from_version_index(item_two)
    assert cache.get_versions_by_model_id(1) == []
    assert 1 not in cache.model_id_index

    # Re-adding should not introduce duplicates
    cache.add_to_version_index(item_two)
    cache.add_to_version_index(item_two)
    assert cache.get_versions_by_model_id('1') == [
        {'versionId': 102, 'name': 'Beta', 'fileName': 'model-a-v2'},
    ]

    # Other model IDs remain accessible
    assert cache.get_versions_by_model_id(2) == [
        {'versionId': 201, 'name': 'Gamma', 'fileName': 'model-b'},
    ]

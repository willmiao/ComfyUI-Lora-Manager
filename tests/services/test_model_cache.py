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


@pytest.mark.asyncio
async def test_version_files_index_tracks_multiple_files_per_version():
    """Two downloaded files of the same version both stay indexed (#1058)."""
    item_a = {
        'file_path': '/models/v1-a.safetensors',
        'file_name': 'model-v1-a',
        'folder': '',
        'civitai': {'id': 301, 'modelId': 3, 'name': 'Multi'},
    }
    item_b = {
        'file_path': '/models/v1-b.safetensors',
        'file_name': 'model-v1-b',
        'folder': '',
        'civitai': {'id': 301, 'modelId': 3, 'name': 'Multi'},
    }

    cache = ModelCache(
        raw_data=[item_a, item_b],
        folders=[],
        name_display_mode='model_name',
    )

    files = cache.get_files_by_version_id(301)
    assert {f['file_path'] for f in files} == {
        '/models/v1-a.safetensors',
        '/models/v1-b.safetensors',
    }

    # Re-adding an existing entry must not duplicate it
    cache.add_to_version_index(item_a)
    assert len(cache.get_files_by_version_id(301)) == 2

    # Removing the indexed file re-points version_index to the sibling
    indexed = cache.version_index[301]
    sibling = item_b if indexed is item_a else item_a
    cache.remove_from_version_index(indexed)

    assert 301 in cache.version_index
    assert cache.version_index[301]['file_path'] == sibling['file_path']
    assert cache.get_versions_by_model_id(3) == [
        {'versionId': 301, 'name': 'Multi', 'fileName': sibling['file_name']},
    ]
    remaining = cache.get_files_by_version_id(301)
    assert [f['file_path'] for f in remaining] == [sibling['file_path']]

    # Removing the last file drops the version from all indexes
    cache.remove_from_version_index(sibling)
    assert 301 not in cache.version_index
    assert cache.get_files_by_version_id(301) == []
    assert cache.get_versions_by_model_id(3) == []
    assert 3 not in cache.model_id_index


@pytest.mark.asyncio
async def test_version_files_index_rebuild_from_raw_data():
    """rebuild_version_index reconstructs the multi-valued index (#1058)."""
    item_a = {
        'file_path': '/models/v1-a.safetensors',
        'file_name': 'model-v1-a',
        'folder': '',
        'civitai': {'id': 401, 'modelId': 4, 'name': 'Multi'},
    }
    item_b = {
        'file_path': '/models/v1-b.safetensors',
        'file_name': 'model-v1-b',
        'folder': '',
        'civitai': {'id': 401, 'modelId': 4, 'name': 'Multi'},
    }

    cache = ModelCache(
        raw_data=[item_a, item_b],
        folders=[],
        name_display_mode='model_name',
    )

    cache.version_files_index = {}
    cache.rebuild_version_index()

    assert len(cache.get_files_by_version_id(401)) == 2
    # Invalid ids normalize to empty results
    assert cache.get_files_by_version_id('not-an-int') == []
    assert cache.get_files_by_version_id(None) == []

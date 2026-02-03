"""Test for duplicate detection by source URL."""
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_find_duplicate_recipes_by_source():
    """Test that duplicate recipes are detected by source URL."""
    from py.services.recipe_scanner import RecipeScanner

    scanner = MagicMock(spec=RecipeScanner)
    scanner.get_cached_data = AsyncMock()
    
    cache = MagicMock()
    cache.raw_data = [
        {
            'id': '8705c972-ef08-47f3-8ac3-9ac3b8ff4c0b',
            'source_path': 'https://civitai.com/images/119165946',
            'title': 'Recipe 1'
        },
        {
            'id': '52e636ce-ea9f-4f64-a6a9-c704bd715889',
            'source_path': 'https://civitai.com/images/119165946',
            'title': 'Recipe 2'
        },
        {
            'id': '00000000-0000-0000-0000-000000000001',
            'source_path': 'https://civitai.com/images/999999999',
            'title': 'Recipe 3'
        },
        {
            'id': '00000000-0000-0000-0000-000000000002',
            'source_path': '',
            'title': 'Recipe 4 (no source)'
        },
    ]
    
    scanner.get_cached_data.return_value = cache
    
    # Call the actual method on the mocked scanner
    from py.services.recipe_scanner import RecipeScanner as RealRecipeScanner
    result = await RealRecipeScanner.find_duplicate_recipes_by_source(scanner)
    
    assert len(result) == 1
    assert 'https://civitai.com/images/119165946' in result
    assert len(result['https://civitai.com/images/119165946']) == 2
    assert '8705c972-ef08-47f3-8ac3-9ac3b8ff4c0b' in result['https://civitai.com/images/119165946']
    assert '52e636ce-ea9f-4f64-a6a9-c704bd715889' in result['https://civitai.com/images/119165946']


@pytest.mark.asyncio
async def test_find_duplicate_recipes_by_source_empty():
    """Test that empty result is returned when no duplicates found."""
    from py.services.recipe_scanner import RecipeScanner

    scanner = MagicMock(spec=RecipeScanner)
    scanner.get_cached_data = AsyncMock()
    
    cache = MagicMock()
    cache.raw_data = [
        {
            'id': '8705c972-ef08-47f3-8ac3-9ac3b8ff4c0b',
            'source_path': 'https://civitai.com/images/119165946',
            'title': 'Recipe 1'
        },
        {
            'id': '00000000-0000-0000-0000-000000000002',
            'source_path': '',
            'title': 'Recipe 2 (no source)'
        },
    ]
    
    scanner.get_cached_data.return_value = cache
    
    from py.services.recipe_scanner import RecipeScanner as RealRecipeScanner
    result = await RealRecipeScanner.find_duplicate_recipes_by_source(scanner)
    
    assert len(result) == 0


@pytest.mark.asyncio
async def test_find_duplicate_recipes_by_source_trimming_whitespace():
    """Test that whitespace is trimmed from source URLs."""
    from py.services.recipe_scanner import RecipeScanner

    scanner = MagicMock(spec=RecipeScanner)
    scanner.get_cached_data = AsyncMock()
    
    cache = MagicMock()
    cache.raw_data = [
        {
            'id': '8705c972-ef08-47f3-8ac3-9ac3b8ff4c0b',
            'source_path': 'https://civitai.com/images/119165946',
            'title': 'Recipe 1'
        },
        {
            'id': '52e636ce-ea9f-4f64-a6a9-c704bd715889',
            'source_path': '  https://civitai.com/images/119165946  ',
            'title': 'Recipe 2'
        },
    ]
    
    scanner.get_cached_data.return_value = cache
    
    from py.services.recipe_scanner import RecipeScanner as RealRecipeScanner
    result = await RealRecipeScanner.find_duplicate_recipes_by_source(scanner)
    
    assert len(result) == 1
    assert 'https://civitai.com/images/119165946' in result
    assert len(result['https://civitai.com/images/119165946']) == 2

"""Tests for RecipeFTSIndex service."""

import os
import pytest
import tempfile
import time
from pathlib import Path

from py.services.recipe_fts_index import RecipeFTSIndex


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path for testing."""
    return str(tmp_path / "test_recipe_fts.sqlite")


@pytest.fixture
def fts_index(temp_db_path):
    """Create a RecipeFTSIndex instance with a temporary database."""
    return RecipeFTSIndex(db_path=temp_db_path)


@pytest.fixture
def sample_recipes():
    """Sample recipe data for testing."""
    return [
        {
            'id': 'recipe-1',
            'title': 'Beautiful Sunset Landscape',
            'tags': ['landscape', 'sunset', 'photography'],
            'loras': [
                {'file_name': 'sunset_lora', 'modelName': 'Sunset Style'},
                {'file_name': 'landscape_v2', 'modelName': 'Landscape Enhancer'},
            ],
            'gen_params': {
                'prompt': '1girl, sunset, beach, golden hour',
                'negative_prompt': 'ugly, blurry, low quality',
            },
        },
        {
            'id': 'recipe-2',
            'title': 'Anime Portrait Style',
            'tags': ['anime', 'portrait', 'character'],
            'loras': [
                {'file_name': 'anime_style_v3', 'modelName': 'Anime Master'},
            ],
            'gen_params': {
                'prompt': '1girl, anime style, beautiful eyes, detailed hair',
                'negative_prompt': 'worst quality, bad anatomy',
            },
        },
        {
            'id': 'recipe-3',
            'title': 'Cyberpunk City Night',
            'tags': ['cyberpunk', 'city', 'night'],
            'loras': [
                {'file_name': 'cyberpunk_neon', 'modelName': 'Neon Lights'},
                {'file_name': 'city_streets', 'modelName': 'Urban Environments'},
            ],
            'gen_params': {
                'prompt': 'cyberpunk city, neon lights, rain, night time',
                'negative_prompt': 'daylight, sunny',
            },
        },
    ]


class TestRecipeFTSIndexInitialization:
    """Tests for FTS index initialization."""

    def test_initialize_creates_database(self, fts_index, temp_db_path):
        """Test that initialize creates the database file."""
        fts_index.initialize()
        assert os.path.exists(temp_db_path)

    def test_initialize_is_idempotent(self, fts_index):
        """Test that calling initialize multiple times is safe."""
        fts_index.initialize()
        fts_index.initialize()
        fts_index.initialize()
        assert fts_index._schema_initialized

    def test_is_ready_false_before_build(self, fts_index):
        """Test that is_ready returns False before index is built."""
        assert not fts_index.is_ready()

    def test_get_database_path(self, fts_index, temp_db_path):
        """Test that get_database_path returns the correct path."""
        assert fts_index.get_database_path() == temp_db_path


class TestRecipeFTSIndexBuild:
    """Tests for FTS index building."""

    def test_build_index_creates_ready_index(self, fts_index, sample_recipes):
        """Test that build_index makes the index ready."""
        fts_index.build_index(sample_recipes)
        assert fts_index.is_ready()

    def test_build_index_counts_recipes(self, fts_index, sample_recipes):
        """Test that build_index indexes all recipes."""
        fts_index.build_index(sample_recipes)
        assert fts_index.get_indexed_count() == len(sample_recipes)

    def test_build_index_empty_list(self, fts_index):
        """Test building index with empty recipe list."""
        fts_index.build_index([])
        assert fts_index.is_ready()
        assert fts_index.get_indexed_count() == 0

    def test_build_index_handles_recipes_without_id(self, fts_index):
        """Test that recipes without ID are skipped."""
        recipes = [
            {'title': 'No ID Recipe', 'tags': ['test']},
            {'id': 'valid-id', 'title': 'Valid Recipe', 'tags': ['test']},
        ]
        fts_index.build_index(recipes)
        assert fts_index.get_indexed_count() == 1

    def test_build_index_handles_missing_fields(self, fts_index):
        """Test that missing optional fields are handled gracefully."""
        recipes = [
            {'id': 'minimal', 'title': 'Minimal Recipe'},
        ]
        fts_index.build_index(recipes)
        assert fts_index.is_ready()
        assert fts_index.get_indexed_count() == 1


class TestRecipeFTSIndexSearch:
    """Tests for FTS search functionality."""

    def test_search_by_title(self, fts_index, sample_recipes):
        """Test searching by recipe title."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('sunset')
        assert 'recipe-1' in results

        results = fts_index.search('anime')
        assert 'recipe-2' in results

    def test_search_by_tags(self, fts_index, sample_recipes):
        """Test searching by recipe tags."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('landscape')
        assert 'recipe-1' in results

        results = fts_index.search('cyberpunk')
        assert 'recipe-3' in results

    def test_search_by_lora_name(self, fts_index, sample_recipes):
        """Test searching by LoRA file name."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('anime_style')
        assert 'recipe-2' in results

        results = fts_index.search('cyberpunk_neon')
        assert 'recipe-3' in results

    def test_search_by_lora_model_name(self, fts_index, sample_recipes):
        """Test searching by LoRA model name."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('Anime Master')
        assert 'recipe-2' in results

    def test_search_by_prompt(self, fts_index, sample_recipes):
        """Test searching by prompt content."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('golden hour')
        assert 'recipe-1' in results

        results = fts_index.search('neon lights')
        assert 'recipe-3' in results

    def test_search_prefix_matching(self, fts_index, sample_recipes):
        """Test that prefix matching works."""
        fts_index.build_index(sample_recipes)

        # 'sun' should match 'sunset'
        results = fts_index.search('sun')
        assert 'recipe-1' in results

        # 'ani' should match 'anime'
        results = fts_index.search('ani')
        assert 'recipe-2' in results

    def test_search_multiple_words(self, fts_index, sample_recipes):
        """Test searching with multiple words (AND logic)."""
        fts_index.build_index(sample_recipes)

        # Both words must match
        results = fts_index.search('city night')
        assert 'recipe-3' in results

    def test_search_case_insensitive(self, fts_index, sample_recipes):
        """Test that search is case-insensitive."""
        fts_index.build_index(sample_recipes)

        results_lower = fts_index.search('sunset')
        results_upper = fts_index.search('SUNSET')
        results_mixed = fts_index.search('SuNsEt')

        assert results_lower == results_upper == results_mixed

    def test_search_no_results(self, fts_index, sample_recipes):
        """Test search with no matching results."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('nonexistent')
        assert len(results) == 0

    def test_search_empty_query(self, fts_index, sample_recipes):
        """Test search with empty query."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('')
        assert len(results) == 0

        results = fts_index.search('   ')
        assert len(results) == 0

    def test_search_not_ready_returns_empty(self, fts_index):
        """Test that search returns empty set when index not ready."""
        results = fts_index.search('test')
        assert len(results) == 0


class TestRecipeFTSIndexFieldRestriction:
    """Tests for field-specific search."""

    def test_search_title_only(self, fts_index, sample_recipes):
        """Test searching only in title field."""
        fts_index.build_index(sample_recipes)

        # 'portrait' appears in title of recipe-2
        results = fts_index.search('portrait', fields={'title'})
        assert 'recipe-2' in results

    def test_search_tags_only(self, fts_index, sample_recipes):
        """Test searching only in tags field."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('photography', fields={'tags'})
        assert 'recipe-1' in results

    def test_search_lora_name_only(self, fts_index, sample_recipes):
        """Test searching only in lora_name field."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('sunset_lora', fields={'lora_name'})
        assert 'recipe-1' in results

    def test_search_prompt_only(self, fts_index, sample_recipes):
        """Test searching only in prompt field."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('golden hour', fields={'prompt'})
        assert 'recipe-1' in results

        # 'ugly' appears in negative_prompt
        results = fts_index.search('ugly', fields={'prompt'})
        assert 'recipe-1' in results

    def test_search_multiple_fields(self, fts_index, sample_recipes):
        """Test searching in multiple fields."""
        fts_index.build_index(sample_recipes)

        results = fts_index.search('sunset', fields={'title', 'tags'})
        assert 'recipe-1' in results

    def test_search_multiple_words_field_restricted(self, fts_index):
        """Test that multi-word searches require ALL words to match within at least one field.

        This is a regression test for the bug where field-restricted multi-word searches
        incorrectly used OR between all word+field combinations, returning recipes that
        only matched some of the search words.
        """
        # Create recipes that test multi-word matching:
        # - recipe-1: both "cute" and "cat" in title
        # - recipe-2: only "cute" in title
        # - recipe-3: both words split across title and tags (should NOT match when searching title only)
        # - recipe-4: both "cute" and "cat" in tags
        # - recipe-5: only "cat" in title
        test_recipes = [
            {
                'id': 'recipe-1',
                'title': 'cute cat photo',
                'tags': ['animal'],
                'loras': [],
                'gen_params': {},
            },
            {
                'id': 'recipe-2',
                'title': 'cute dog picture',
                'tags': ['pet'],
                'loras': [],
                'gen_params': {},
            },
            {
                'id': 'recipe-3',
                'title': 'cute',
                'tags': ['cat', 'animal'],  # "cute" in title, "cat" in tags
                'loras': [],
                'gen_params': {},
            },
            {
                'id': 'recipe-4',
                'title': 'kitten image',
                'tags': ['cute', 'cat'],  # both words in tags
                'loras': [],
                'gen_params': {},
            },
            {
                'id': 'recipe-5',
                'title': 'cat only',
                'tags': [],
                'loras': [],
                'gen_params': {},
            },
        ]
        fts_index.build_index(test_recipes)

        # Search "cute cat" in title only - should only match recipe-1 (both words in title)
        results = fts_index.search('cute cat', fields={'title'})
        assert results == {'recipe-1'}, f"Expected only recipe-1, got {results}"

        # Search "cute cat" in tags only - should only match recipe-4 (both words in tags)
        results = fts_index.search('cute cat', fields={'tags'})
        assert results == {'recipe-4'}, f"Expected only recipe-4, got {results}"

        # Search "cute cat" in both title and tags - should match recipe-1 and recipe-4
        # (each has both words in one of the specified fields)
        results = fts_index.search('cute cat', fields={'title', 'tags'})
        assert results == {'recipe-1', 'recipe-4'}, f"Expected recipe-1 and recipe-4, got {results}"

        # Search without field restriction - should match recipes where words appear in any indexed field
        results = fts_index.search('cute cat')
        # recipe-1, recipe-2 (cute), recipe-3 (cute in title, cat in tags), recipe-4, recipe-5 (cat)
        # Actually, without field restriction, FTS searches all fields as one bag of content
        # So any recipe with both "cute" and "cat" anywhere should match
        assert 'recipe-1' in results  # both in title
        assert 'recipe-4' in results  # both in tags
        # recipe-3: "cute" in title, "cat" in tags - both words present
        assert 'recipe-3' in results


class TestRecipeFTSIndexIncrementalOperations:
    """Tests for incremental add/remove/update operations."""

    def test_add_recipe(self, fts_index, sample_recipes):
        """Test adding a single recipe to the index."""
        fts_index.build_index(sample_recipes)
        initial_count = fts_index.get_indexed_count()

        new_recipe = {
            'id': 'recipe-new',
            'title': 'New Fantasy Scene',
            'tags': ['fantasy', 'magic'],
            'loras': [{'file_name': 'fantasy_lora', 'modelName': 'Fantasy Style'}],
            'gen_params': {'prompt': 'magical forest, wizard'},
        }
        fts_index.add_recipe(new_recipe)

        assert fts_index.get_indexed_count() == initial_count + 1
        assert 'recipe-new' in fts_index.search('fantasy')

    def test_remove_recipe(self, fts_index, sample_recipes):
        """Test removing a recipe from the index."""
        fts_index.build_index(sample_recipes)
        initial_count = fts_index.get_indexed_count()

        # Verify recipe-1 is searchable
        assert 'recipe-1' in fts_index.search('sunset')

        # Remove it
        fts_index.remove_recipe('recipe-1')

        # Verify it's gone
        assert fts_index.get_indexed_count() == initial_count - 1
        assert 'recipe-1' not in fts_index.search('sunset')

    def test_update_recipe(self, fts_index, sample_recipes):
        """Test updating a recipe in the index."""
        fts_index.build_index(sample_recipes)

        # Update recipe-1 title
        updated_recipe = {
            'id': 'recipe-1',
            'title': 'Tropical Beach Paradise',  # Changed from 'Beautiful Sunset Landscape'
            'tags': ['beach', 'tropical'],  # Changed tags
            'loras': sample_recipes[0]['loras'],
            'gen_params': sample_recipes[0]['gen_params'],
        }
        fts_index.update_recipe(updated_recipe)

        # Old title should not match
        results = fts_index.search('sunset', fields={'title'})
        assert 'recipe-1' not in results

        # New title should match
        results = fts_index.search('tropical', fields={'title'})
        assert 'recipe-1' in results

    def test_add_recipe_not_ready(self, fts_index):
        """Test that add_recipe returns False when index not ready."""
        recipe = {'id': 'test', 'title': 'Test'}
        result = fts_index.add_recipe(recipe)
        assert result is False

    def test_remove_recipe_not_ready(self, fts_index):
        """Test that remove_recipe returns False when index not ready."""
        result = fts_index.remove_recipe('test')
        assert result is False


class TestRecipeFTSIndexClear:
    """Tests for clearing the FTS index."""

    def test_clear_index(self, fts_index, sample_recipes):
        """Test clearing all data from the index."""
        fts_index.build_index(sample_recipes)
        assert fts_index.get_indexed_count() > 0

        fts_index.clear()
        assert fts_index.get_indexed_count() == 0
        assert not fts_index.is_ready()


class TestRecipeFTSIndexSpecialCharacters:
    """Tests for handling special characters in search."""

    def test_search_with_special_characters(self, fts_index):
        """Test that special characters are handled safely."""
        recipes = [
            {'id': 'r1', 'title': 'Test (with) parentheses', 'tags': []},
            {'id': 'r2', 'title': 'Test "with" quotes', 'tags': []},
            {'id': 'r3', 'title': 'Test:with:colons', 'tags': []},
        ]
        fts_index.build_index(recipes)

        # These should not crash
        results = fts_index.search('(with)')
        results = fts_index.search('"with"')
        results = fts_index.search(':with:')

        # Basic word should still match
        results = fts_index.search('test')
        assert len(results) == 3

    def test_search_unicode_characters(self, fts_index):
        """Test searching with unicode characters."""
        recipes = [
            {'id': 'r1', 'title': '日本語テスト', 'tags': ['anime']},
            {'id': 'r2', 'title': 'Émilie résumé café', 'tags': ['french']},
        ]
        fts_index.build_index(recipes)

        # Unicode search
        results = fts_index.search('日本')
        assert 'r1' in results

        # Diacritics (depends on tokenizer settings)
        results = fts_index.search('cafe')  # Should match café due to remove_diacritics
        # Note: Result depends on FTS5 configuration


class TestRecipeFTSIndexPerformance:
    """Basic performance tests."""

    def test_build_large_index(self, fts_index):
        """Test building index with many recipes."""
        recipes = [
            {
                'id': f'recipe-{i}',
                'title': f'Recipe Title {i} with words like sunset landscape anime cyberpunk',
                'tags': ['tag1', 'tag2', 'tag3'],
                'loras': [{'file_name': f'lora_{i}', 'modelName': f'Model {i}'}],
                'gen_params': {'prompt': f'test prompt {i}', 'negative_prompt': 'bad'},
            }
            for i in range(1000)
        ]

        start_time = time.time()
        fts_index.build_index(recipes)
        build_time = time.time() - start_time

        assert fts_index.is_ready()
        assert fts_index.get_indexed_count() == 1000
        # Build should complete reasonably fast (under 5 seconds)
        assert build_time < 5.0

    def test_search_large_index(self, fts_index):
        """Test searching a large index."""
        recipes = [
            {
                'id': f'recipe-{i}',
                'title': f'Recipe Title {i}',
                'tags': ['common_tag'],
                'loras': [],
                'gen_params': {},
            }
            for i in range(1000)
        ]
        fts_index.build_index(recipes)

        start_time = time.time()
        results = fts_index.search('common_tag')
        search_time = time.time() - start_time

        assert len(results) == 1000
        # Search should be very fast (under 100ms)
        assert search_time < 0.1

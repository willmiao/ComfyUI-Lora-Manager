"""Tests for TagFTSIndex functionality."""

import os
import tempfile
from typing import List

import pytest

from py.services.tag_fts_index import (
    TagFTSIndex,
    CATEGORY_NAMES,
    CATEGORY_NAME_TO_IDS,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.unlink(wal_path)


@pytest.fixture
def temp_csv_path():
    """Create a temporary CSV file with test data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Write test data in the same format as danbooru_e621_merged.csv
        # Format: tag_name,category,post_count,aliases
        f.write('1girl,0,6008644,"1girls,sole_female"\n')
        f.write('highres,5,5256195,"high_res,high_resolution,hires"\n')
        f.write('solo,0,5000954,"alone,female_solo,single"\n')
        f.write('hatsune_miku,4,500000,"miku"\n')
        f.write('konpaku_youmu,4,150000,"youmu"\n')
        f.write('artist_request,1,100000,""\n')
        f.write('touhou,3,300000,"touhou_project"\n')
        f.write('mammal,12,3437444,"cetancodont"\n')
        f.write('anthro,7,3381927,"anthropomorphic"\n')
        f.write('hi_res,14,3116617,"high_res"\n')
        path = f.name
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


class TestTagFTSIndexBasic:
    """Basic tests for TagFTSIndex initialization and schema."""

    def test_initialize_creates_tables(self, temp_db_path, temp_csv_path):
        """Test that initialization creates required tables."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        fts.initialize()

        assert fts._schema_initialized is True

    def test_get_database_path(self, temp_db_path, temp_csv_path):
        """Test get_database_path returns correct path."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        assert fts.get_database_path() == temp_db_path

    def test_get_csv_path(self, temp_db_path, temp_csv_path):
        """Test get_csv_path returns correct path."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        assert fts.get_csv_path() == temp_csv_path

    def test_is_ready_initially_false(self, temp_db_path, temp_csv_path):
        """Test that is_ready returns False before building index."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        assert fts.is_ready() is False


class TestTagFTSIndexBuild:
    """Tests for building the FTS index."""

    def test_build_index_from_csv(self, temp_db_path, temp_csv_path):
        """Test building index from CSV file."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        fts.build_index()

        assert fts.is_ready() is True
        assert fts.get_indexed_count() == 10

    def test_build_index_nonexistent_csv(self, temp_db_path):
        """Test that build_index handles missing CSV gracefully."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path="/nonexistent/path.csv")
        fts.build_index()

        assert fts.is_ready() is False
        assert fts.get_indexed_count() == 0

    def test_ensure_ready_builds_index(self, temp_db_path, temp_csv_path):
        """Test that ensure_ready builds index if not ready."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)

        # Initially not ready
        assert fts.is_ready() is False

        # ensure_ready should build the index
        result = fts.ensure_ready()

        assert result is True
        assert fts.is_ready() is True


class TestTagFTSIndexSearch:
    """Tests for searching the FTS index."""

    @pytest.fixture
    def populated_fts(self, temp_db_path, temp_csv_path):
        """Create a populated FTS index."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        fts.build_index()
        return fts

    def test_search_basic(self, populated_fts):
        """Test basic search functionality."""
        results = populated_fts.search("1girl")

        assert len(results) >= 1
        assert any(r["tag_name"] == "1girl" for r in results)

    def test_search_prefix(self, populated_fts):
        """Test prefix matching."""
        results = populated_fts.search("hatsu")

        assert len(results) >= 1
        assert any(r["tag_name"] == "hatsune_miku" for r in results)

    def test_search_returns_enriched_results(self, populated_fts):
        """Test that search returns enriched results with category and post_count."""
        results = populated_fts.search("miku")

        assert len(results) >= 1
        result = results[0]

        assert "tag_name" in result
        assert "category" in result
        assert "post_count" in result
        assert result["tag_name"] == "hatsune_miku"
        assert result["category"] == 4  # Character category
        assert result["post_count"] == 500000

    def test_search_with_category_filter(self, populated_fts):
        """Test searching with category filter."""
        # Search for character tags only (categories 4 and 11)
        results = populated_fts.search("konpaku", categories=[4, 11])

        assert len(results) >= 1
        assert all(r["category"] in [4, 11] for r in results)

    def test_search_with_category_filter_excludes_others(self, populated_fts):
        """Test that category filter excludes other categories."""
        # Search for "hi" but only in general category
        results = populated_fts.search("hi", categories=[0, 7])

        # Should not include "highres" (meta category 5) or "hi_res" (meta category 14)
        assert all(r["category"] in [0, 7] for r in results)

    def test_search_empty_query_returns_empty(self, populated_fts):
        """Test that empty query returns empty results."""
        results = populated_fts.search("")
        assert results == []

    def test_search_no_matches_returns_empty(self, populated_fts):
        """Test that query with no matches returns empty results."""
        results = populated_fts.search("zzzznonexistent")
        assert results == []

    def test_search_results_sorted_by_post_count(self, populated_fts):
        """Test that results are sorted by post_count descending."""
        results = populated_fts.search("1girl", limit=10)

        # Verify results are sorted by post_count descending
        post_counts = [r["post_count"] for r in results]
        assert post_counts == sorted(post_counts, reverse=True)

    def test_search_limit(self, populated_fts):
        """Test search result limiting."""
        results = populated_fts.search("girl", limit=1)
        assert len(results) <= 1


class TestAliasSearch:
    """Tests for alias search functionality."""

    @pytest.fixture
    def populated_fts(self, temp_db_path, temp_csv_path):
        """Create a populated FTS index."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        fts.build_index()
        return fts

    def test_search_by_alias_returns_canonical_tag(self, populated_fts):
        """Test that searching by alias returns the canonical tag with matched_alias."""
        # Search for "miku" which is an alias for "hatsune_miku"
        results = populated_fts.search("miku")

        assert len(results) >= 1
        hatsune_result = next((r for r in results if r["tag_name"] == "hatsune_miku"), None)
        assert hatsune_result is not None
        assert hatsune_result["matched_alias"] == "miku"

    def test_search_by_canonical_name_no_matched_alias(self, populated_fts):
        """Test that searching by canonical name does not set matched_alias."""
        # Search for "hatsune" which directly matches "hatsune_miku"
        results = populated_fts.search("hatsune")

        assert len(results) >= 1
        hatsune_result = next((r for r in results if r["tag_name"] == "hatsune_miku"), None)
        assert hatsune_result is not None
        assert "matched_alias" not in hatsune_result

    def test_search_by_prefix_alias(self, populated_fts):
        """Test prefix matching on aliases."""
        # "1girls" is an alias for "1girl" - search by prefix "1gir"
        results = populated_fts.search("1gir")

        assert len(results) >= 1
        result = next((r for r in results if r["tag_name"] == "1girl"), None)
        assert result is not None
        # Should not have matched_alias since "1girl" starts with "1gir"
        assert "matched_alias" not in result

    def test_alias_search_with_category_filter(self, populated_fts):
        """Test that alias search works with category filtering."""
        # Search for "youmu" (alias for konpaku_youmu) with character category filter
        results = populated_fts.search("youmu", categories=[4, 11])

        assert len(results) >= 1
        result = results[0]
        assert result["tag_name"] == "konpaku_youmu"
        assert result["matched_alias"] == "youmu"
        assert result["category"] in [4, 11]

    def test_tag_without_aliases_still_works(self, populated_fts):
        """Test that tags without aliases still work correctly."""
        # "artist_request" has no aliases
        results = populated_fts.search("artist_req")

        assert len(results) >= 1
        result = next((r for r in results if r["tag_name"] == "artist_request"), None)
        assert result is not None
        assert "matched_alias" not in result

    def test_multiple_aliases_first_match_returned(self, populated_fts):
        """Test that when multiple aliases could match, the first one is returned."""
        # "highres" has aliases: "high_res,high_resolution,hires"
        # Searching for "high_r" should match "high_res" first
        results = populated_fts.search("high_r")

        assert len(results) >= 1
        highres_result = next((r for r in results if r["tag_name"] == "highres"), None)
        assert highres_result is not None
        assert highres_result["matched_alias"] == "high_res"

    def test_search_by_short_alias(self, populated_fts):
        """Test searching by a short alias."""
        # "/lh" style short aliases - using "hires" which is short for highres
        results = populated_fts.search("hires")

        assert len(results) >= 1
        result = next((r for r in results if r["tag_name"] == "highres"), None)
        assert result is not None
        assert result["matched_alias"] == "hires"

    def test_search_by_word_within_alias(self, populated_fts):
        """Test searching by a word within a compound alias like 'sole_female'."""
        # "sole_female" is an alias for "1girl"
        # Searching "female" should match "1girl" with matched_alias "sole_female"
        results = populated_fts.search("female")

        assert len(results) >= 1
        result = next((r for r in results if r["tag_name"] == "1girl"), None)
        assert result is not None
        assert result["matched_alias"] == "sole_female"

    def test_search_by_second_word_in_alias(self, populated_fts):
        """Test that searching for second word in underscore-separated alias works."""
        # "female_solo" is an alias for "solo"
        # Searching "solo" would match the tag directly, but let's test another case
        # "single" is an alias for "solo" - straightforward match
        results = populated_fts.search("single")

        assert len(results) >= 1
        result = next((r for r in results if r["tag_name"] == "solo"), None)
        assert result is not None
        assert result["matched_alias"] == "single"


class TestSlashPrefixAliases:
    """Tests for slash-prefixed alias search (e.g., /lh for long_hair)."""

    @pytest.fixture
    def fts_with_slash_aliases(self, temp_db_path):
        """Create an FTS index with slash-prefixed aliases."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            # Format: tag_name,category,post_count,aliases
            f.write('long_hair,0,4350743,"/lh,longhair,very_long_hair"\n')
            f.write('breasts,0,3439214,"/b,boobs,oppai"\n')
            f.write('short_hair,0,1500000,"/sh,shorthair"\n')
            csv_path = f.name

        try:
            fts = TagFTSIndex(db_path=temp_db_path, csv_path=csv_path)
            fts.build_index()
            yield fts
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

    def test_search_slash_alias_with_slash(self, fts_with_slash_aliases):
        """Test searching with slash prefix returns correct result."""
        results = fts_with_slash_aliases.search("/lh")

        assert len(results) >= 1
        result = results[0]
        assert result["tag_name"] == "long_hair"
        assert result["matched_alias"] == "/lh"

    def test_search_slash_alias_without_slash(self, fts_with_slash_aliases):
        """Test searching without slash prefix also works."""
        results = fts_with_slash_aliases.search("lh")

        assert len(results) >= 1
        result = results[0]
        assert result["tag_name"] == "long_hair"
        assert result["matched_alias"] == "/lh"

    def test_search_regular_alias_still_works(self, fts_with_slash_aliases):
        """Test that non-slash aliases still work."""
        results = fts_with_slash_aliases.search("longhair")

        assert len(results) >= 1
        result = results[0]
        assert result["tag_name"] == "long_hair"
        assert result["matched_alias"] == "longhair"

    def test_direct_tag_name_search(self, fts_with_slash_aliases):
        """Test that direct tag name search doesn't show alias."""
        results = fts_with_slash_aliases.search("long_hair")

        assert len(results) >= 1
        result = results[0]
        assert result["tag_name"] == "long_hair"
        assert "matched_alias" not in result


class TestTagFTSIndexClear:
    """Tests for clearing the FTS index."""

    def test_clear_removes_all_data(self, temp_db_path, temp_csv_path):
        """Test that clear removes all indexed data."""
        fts = TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)
        fts.build_index()

        assert fts.get_indexed_count() > 0

        fts.clear()

        assert fts.get_indexed_count() == 0
        assert fts.is_ready() is False


class TestCategoryMappings:
    """Tests for category name mappings."""

    def test_category_names_complete(self):
        """Test that CATEGORY_NAMES includes all expected categories."""
        expected_categories = [0, 1, 3, 4, 5, 7, 8, 10, 11, 12, 14, 15]
        for cat in expected_categories:
            assert cat in CATEGORY_NAMES

    def test_category_name_to_ids_complete(self):
        """Test that CATEGORY_NAME_TO_IDS includes all expected names."""
        expected_names = ["general", "artist", "copyright", "character", "meta", "species", "lore"]
        for name in expected_names:
            assert name in CATEGORY_NAME_TO_IDS
            assert isinstance(CATEGORY_NAME_TO_IDS[name], list)
            assert len(CATEGORY_NAME_TO_IDS[name]) > 0

    def test_category_name_to_ids_includes_both_platforms(self):
        """Test that category mappings include both Danbooru and e621 IDs where applicable."""
        # General should have both Danbooru (0) and e621 (7)
        assert 0 in CATEGORY_NAME_TO_IDS["general"]
        assert 7 in CATEGORY_NAME_TO_IDS["general"]

        # Character should have both Danbooru (4) and e621 (11)
        assert 4 in CATEGORY_NAME_TO_IDS["character"]
        assert 11 in CATEGORY_NAME_TO_IDS["character"]


class TestFTSQueryBuilding:
    """Tests for FTS query building."""

    @pytest.fixture
    def fts_instance(self, temp_db_path, temp_csv_path):
        """Create an FTS instance for testing."""
        return TagFTSIndex(db_path=temp_db_path, csv_path=temp_csv_path)

    def test_build_fts_query_simple(self, fts_instance):
        """Test FTS query building with simple query."""
        query = fts_instance._build_fts_query("test")
        assert query == "test*"

    def test_build_fts_query_multiple_words(self, fts_instance):
        """Test FTS query building with multiple words."""
        query = fts_instance._build_fts_query("test query")
        assert query == "test* query*"

    def test_build_fts_query_escapes_special_chars(self, fts_instance):
        """Test that special characters are escaped."""
        query = fts_instance._build_fts_query("test:query")
        # Colon should be replaced with space
        assert ":" not in query

    def test_build_fts_query_empty_returns_empty(self, fts_instance):
        """Test that empty query returns empty string."""
        query = fts_instance._build_fts_query("")
        assert query == ""

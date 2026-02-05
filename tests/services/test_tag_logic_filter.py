"""Tests for tag logic (OR/AND) filtering functionality."""

import pytest
from py.services.model_query import ModelFilterSet, FilterCriteria


class StubSettings:
    def get(self, key, default=None):
        return default


class TestTagLogicFilter:
    """Test cases for tag_logic parameter in FilterCriteria."""

    def test_tag_logic_any_returns_items_with_any_tag(self):
        """Test that tag_logic='any' (OR) returns items matching any include tag."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
            {"name": "m4", "tags": ["style"]},
            {"name": "m5", "tags": []},
        ]

        # Include anime OR realistic (should match m1, m2, m3)
        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"},
            tag_logic="any"
        )
        result = filter_set.apply(data, criteria)
        assert len(result) == 3
        assert {item["name"] for item in result} == {"m1", "m2", "m3"}

    def test_tag_logic_all_returns_items_with_all_tags(self):
        """Test that tag_logic='all' (AND) returns only items matching all include tags."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
            {"name": "m4", "tags": ["style"]},
            {"name": "m5", "tags": []},
        ]

        # Include anime AND realistic (should match only m3)
        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"},
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        assert len(result) == 1
        assert result[0]["name"] == "m3"

    def test_tag_logic_all_with_single_tag(self):
        """Test that tag_logic='all' with single tag works same as 'any'."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
        ]

        # Include only anime with 'all' logic
        criteria = FilterCriteria(
            tags={"anime": "include"},
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        assert len(result) == 2
        assert {item["name"] for item in result} == {"m1", "m3"}

    def test_tag_logic_any_with_exclude_tags(self):
        """Test that tag_logic='any' works correctly with exclude tags."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
            {"name": "m4", "tags": ["nsfw"]},
            {"name": "m5", "tags": ["anime", "nsfw"]},
        ]

        # Include anime OR realistic, exclude nsfw
        criteria = FilterCriteria(
            tags={
                "anime": "include",
                "realistic": "include",
                "nsfw": "exclude"
            },
            tag_logic="any"
        )
        result = filter_set.apply(data, criteria)
        # Should match m1 (anime), m2 (realistic), m3 (both)
        # m4 excluded by nsfw, m5 excluded by nsfw
        assert len(result) == 3
        assert {item["name"] for item in result} == {"m1", "m2", "m3"}

    def test_tag_logic_all_with_exclude_tags(self):
        """Test that tag_logic='all' works correctly with exclude tags."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime", "character"]},
            {"name": "m2", "tags": ["realistic", "character"]},
            {"name": "m3", "tags": ["anime", "realistic", "character"]},
            {"name": "m4", "tags": ["anime", "character", "nsfw"]},
        ]

        # Include anime AND character, exclude nsfw
        criteria = FilterCriteria(
            tags={
                "anime": "include",
                "character": "include",
                "nsfw": "exclude"
            },
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        # m1: has anime+character, no nsfw ✓
        # m2: missing anime ✗
        # m3: has anime+character, no nsfw ✓
        # m4: has anime+character but also nsfw ✗
        assert len(result) == 2
        assert {item["name"] for item in result} == {"m1", "m3"}

    def test_tag_logic_all_with_no_tags_special_case(self):
        """Test tag_logic='all' with __no_tags__ special tag.
        
        When __no_tags__ is used with 'all' logic along with regular tags,
        the behavior is: items with no tags are returned (since they satisfy
        __no_tags__), OR items that have all the regular tags.
        This is because __no_tags__ is a special condition that can't be ANDed
        with regular tags in a meaningful way.
        """
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": []},
            {"name": "m3", "tags": None},
            {"name": "m4", "tags": ["anime", "character"]},
        ]

        # Include anime AND __no_tags__ with 'all' logic
        # Implementation treats this as: no tags OR (all regular tags)
        criteria = FilterCriteria(
            tags={"anime": "include", "__no_tags__": "include"},
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        # Items with no tags: m2, m3
        # Items with all regular tags (anime): m1, m4
        # Combined: m1, m2, m3, m4 (all items)
        assert len(result) == 4

    def test_tag_logic_any_with_no_tags_special_case(self):
        """Test tag_logic='any' with __no_tags__ special tag."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": []},
            {"name": "m3", "tags": None},
            {"name": "m4", "tags": ["realistic"]},
        ]

        # Include anime OR __no_tags__
        criteria = FilterCriteria(
            tags={"anime": "include", "__no_tags__": "include"},
            tag_logic="any"
        )
        result = filter_set.apply(data, criteria)
        # Should match m1 (anime), m2 (no tags), m3 (no tags)
        assert len(result) == 3
        assert {item["name"] for item in result} == {"m1", "m2", "m3"}

    def test_tag_logic_default_is_any(self):
        """Test that default tag_logic is 'any' when not specified."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
        ]

        # Not specifying tag_logic should default to 'any'
        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"}
        )
        result = filter_set.apply(data, criteria)
        # Should match m1, m2, m3 (OR behavior)
        assert len(result) == 3
        assert {item["name"] for item in result} == {"m1", "m2", "m3"}

    def test_tag_logic_case_insensitive(self):
        """Test that tag_logic values are case insensitive."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
            {"name": "m3", "tags": ["anime", "realistic"]},
        ]

        # Test uppercase 'ALL'
        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"},
            tag_logic="ALL"
        )
        result = filter_set.apply(data, criteria)
        assert len(result) == 1
        assert result[0]["name"] == "m3"

        # Test mixed case 'Any'
        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"},
            tag_logic="Any"
        )
        result = filter_set.apply(data, criteria)
        assert len(result) == 3

    def test_tag_logic_all_with_three_tags(self):
        """Test tag_logic='all' with three include tags."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["anime", "character"]},
            {"name": "m3", "tags": ["anime", "character", "style"]},
            {"name": "m4", "tags": ["character", "style"]},
        ]

        # Include anime AND character AND style
        criteria = FilterCriteria(
            tags={
                "anime": "include",
                "character": "include",
                "style": "include"
            },
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        # Only m3 has all three tags
        assert len(result) == 1
        assert result[0]["name"] == "m3"

    def test_tag_logic_empty_include_tags(self):
        """Test that empty include tags with any logic returns all items."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime"]},
            {"name": "m2", "tags": ["realistic"]},
        ]

        # Only exclude tags, no include tags
        criteria = FilterCriteria(
            tags={"nsfw": "exclude"},
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        # Both should match since no include filters
        assert len(result) == 2

    def test_tag_logic_with_none_tags_field(self):
        """Test tag_logic handles items with None tags field."""
        filter_set = ModelFilterSet(StubSettings())
        data = [
            {"name": "m1", "tags": ["anime", "realistic"]},
            {"name": "m2", "tags": None},
            {"name": "m3", "tags": ["anime"]},
        ]

        criteria = FilterCriteria(
            tags={"anime": "include", "realistic": "include"},
            tag_logic="all"
        )
        result = filter_set.apply(data, criteria)
        # Only m1 has both anime and realistic
        assert len(result) == 1
        assert result[0]["name"] == "m1"

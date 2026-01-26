"""Tests for CustomWordsService with TagFTSIndex integration."""

import pytest

from py.services.custom_words_service import CustomWordsService, get_custom_words_service


class TestCustomWordsService:
    """Test CustomWordsService functionality."""

    def test_singleton_instance(self):
        service1 = get_custom_words_service()
        service2 = get_custom_words_service()
        assert service1 is service2

    def test_search_words_without_tag_index(self):
        service = CustomWordsService.__new__(CustomWordsService)

        def mock_get_index():
            return None

        service._get_tag_index = mock_get_index

        results = service.search_words("test", limit=10)
        assert results == []

    def test_search_words_with_tag_index(self):
        service = CustomWordsService.__new__(CustomWordsService)
        mock_tag_index = MockTagFTSIndex()

        def mock_get_index():
            return mock_tag_index

        service._get_tag_index = mock_get_index

        results = service.search_words("miku", limit=20)
        assert len(results) == 2
        assert results[0]["tag_name"] == "hatsune_miku"
        assert results[0]["category"] == 4
        assert results[0]["post_count"] == 500000

    def test_search_words_with_category_filter(self):
        service = CustomWordsService.__new__(CustomWordsService)
        mock_tag_index = MockTagFTSIndex()

        def mock_get_index():
            return mock_tag_index

        service._get_tag_index = mock_get_index

        results = service.search_words("miku", categories=[4, 11], limit=20)
        assert len(results) == 2
        assert results[0]["tag_name"] == "hatsune_miku"
        assert results[0]["category"] == 4
        assert results[1]["tag_name"] == "hatsune_miku_(vocaloid)"
        assert results[1]["category"] == 4

    def test_search_words_respects_limit(self):
        service = CustomWordsService.__new__(CustomWordsService)
        mock_tag_index = MockTagFTSIndex()

        def mock_get_index():
            return mock_tag_index

        service._get_tag_index = mock_get_index

        results = service.search_words("miku", limit=1)
        assert len(results) <= 1

    def test_search_words_empty_term(self):
        service = CustomWordsService.__new__(CustomWordsService)
        mock_tag_index = MockTagFTSIndex()

        def mock_get_index():
            return mock_tag_index

        service._get_tag_index = mock_get_index

        results = service.search_words("", limit=20)
        assert results == []

    def test_search_words_uses_tag_index(self):
        service = CustomWordsService.__new__(CustomWordsService)
        mock_tag_index = MockTagFTSIndex()

        def mock_get_index():
            return mock_tag_index

        service._get_tag_index = mock_get_index

        results = service.search_words("test")
        assert mock_tag_index.called


class MockTagFTSIndex:
    """Mock TagFTSIndex for testing."""

    def __init__(self):
        self.called = False
        self._results = [
            {"tag_name": "hatsune_miku", "category": 4, "post_count": 500000},
            {"tag_name": "hatsune_miku_(vocaloid)", "category": 4, "post_count": 250000},
        ]

    def search(self, query, categories=None, limit=20):
        self.called = True
        if not query:
            return []
        if categories:
            return [r for r in self._results if r["category"] in categories][:limit]
        return self._results[:limit]
